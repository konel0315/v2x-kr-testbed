"""가상 OBU: SUMO 차량에 달린 단말기.

  - 시작: OpenSCMS(SCMS)에서 받은 응용인증서를 쓴다 (BSM 권한, scripts/provision.py)
  - 보내기: 내 차 상태로 J2735 BSM을 만들어 IEEE 1609.2로 서명하고 0.1초마다 방송
  - 받기:   검증(1 서명  2 권한(PSID)  3 유효기간  4 발급 체인)을 통과한 것만 쓴다
      V2I  RSU가 방송한 SPaT(신호)·MAP(교차로 지도)
      V2P  보행자 스마트폰이 방송한 PSM(보행자 위치)
      V2N  교통센터가 휴대폰망(TLS)으로 보낸 TIM(공사 구간 안내). 같은 TIM이 RSU로도 온다(하이브리드)
  - 휴대폰망으로 1초마다 내 BSM을 교통센터에 올린다 (V2N 위치 보고)
  - 협력주행(--coop): SUMO 신호등은 무시하고, V2X로 받은 정보만 보고 주행
      빨간불이면 정지선 앞에 서고, 앞길에 보행자가 있거나 들어오려 하면 서고,
      공사 구간에서는 권고 속도로 줄인다

사용법 (OpenSCMS 인증서 준비와 SUMO(--num-clients 4)를 먼저. 3번째는 tsc, 4번째는 보행자):
    python3 obu/obu.py --vehicle obu1 --order 1 [--coop]
"""
import argparse
import math
import os
import sys
import time

import traci

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import geo, intersection, j2735, psid, sec1609, v2n, wsmp  # noqa: E402
from common.identity import Identity  # noqa: E402
from common.radio import Radio  # noqa: E402
from common.v2xlog import V2XLog  # noqa: E402

STEP = 0.1              # SUMO 한 스텝 = 0.1초 = BSM 10 Hz
DECEL = 3.0             # 정지할 때 쓸 감속도 (m/s^2)
STOP_GAP = 2.0          # 정지선 몇 m 앞에서 설지
SPAT_TIMEOUT = 1.0      # SPaT를 이 시간 넘게 못 받으면 신호를 모른다고 보고 감속
ROAD_SPEED = 13.89      # 제한속도 (m/s)

# V2P: 보행자 보호
PSM_TIMEOUT = 1.0       # 이 시간 넘게 소식이 없는 보행자는 잊는다
PED_LOOKAHEAD = 60.0    # 앞으로 몇 m 안의 보행자를 본다
PED_CORRIDOR = 3.5      # 내 진행 경로 중심에서 좌우 몇 m 안이면 '내 길 위' (차로 반폭 1.6 + 차 반폭 0.9 + 여유 1.0)
PED_PREDICT = 2.0       # 보행자가 몇 초 뒤 내 길에 들어올지까지 본다
PED_GAP = 4.0           # 보행자 몇 m 앞에서 설지 (차 앞범퍼 기준)

# V2N: 공사 구간
TIM_TIMEOUT = 3.0       # 이 시간 넘게 TIM을 못 받으면 안내가 끝난 것으로 본다
ZONE_DECEL = 1.5        # 공사 구간 앞에서 천천히 줄이는 감속도
ZONE_ANGLE = 45.0       # 공사 구간 쪽으로 가고 있는지 판단하는 각도


def read_vehicle(vid):
    """SUMO에서 차량 상태를 읽어 BSM에 필요한 값으로 돌려준다. 차가 없으면 None."""
    if vid not in traci.vehicle.getIDList():
        return None
    x, y = traci.vehicle.getPosition(vid)
    lon, lat = traci.simulation.convertGeo(x, y)
    return {
        "lat": lat,                                  # 위도 (도)
        "lon": lon,                                  # 경도 (도)
        "speed": traci.vehicle.getSpeed(vid),        # m/s
        "heading": traci.vehicle.getAngle(vid),      # 북쪽 0도, 시계 방향
        "accel": traci.vehicle.getAcceleration(vid), # m/s^2
    }


class V2XView:
    """V2X로 받은 정보만으로 만든 '내가 아는 교차로 상태'."""

    def __init__(self, log, verifier):
        self.map = None
        self.signals = {}          # signalGroup -> (eventState, minEndTime)
        self.spat_time = None
        self.log = log
        self.verifier = verifier   # SCMS 신뢰 목록(루트·ICA·ACA)으로 만든 검증기
        self.count = {"SPAT": 0, "MAP": 0, "PSM": 0, "TIM(V2X)": 0, "TIM(V2N)": 0}
        self.rejected = {}         # 거부 이유 -> 개수
        self.peds = {}             # 보행자 서명 인증서 번호 -> (상태, 받은 시각)
        self.zones = {}            # TIM packetID -> (구간 목록, 받은 시각, 경로들)

    def _reject(self, mtype, sender, reason, step, t0):
        self.rejected[reason] = self.rejected.get(reason, 0) + 1
        self.log.write(mtype, sender, "REJECT", reason, auth_status="INVALID",
                       fail_step=step, t_start=t0)

    def handle(self, wsm, path="V2X"):
        """path: 'V2X'(직접통신, 가상 무선) 또는 'V2N'(휴대폰망)"""
        t0 = time.perf_counter()
        try:
            p, data = wsmp.decode(wsm)
        except ValueError:
            return
        if p not in (psid.SPAT, psid.MAP, psid.PSM, psid.TIM):
            return                                    # 다른 차의 BSM 등은 여기서 안 씀
        mtype, sender, auth = psid.NAMES[p], "?", "NOT_CHECKED"
        if p == psid.TIM:
            mtype = f"TIM({path})"
        # ---- 1609.2 검증: 통과한 것만 쓴다
        if not sec1609.is_spdu(data):
            return self._reject(mtype, sender, "UNSIGNED", 1, t0)
        try:
            data, cert = self.verifier.verify(data, p)
        except sec1609.VerifyError as e:
            return self._reject(mtype, sender, e.reason, e.step, t0)
        sender, auth = cert.name, "VALID"
        try:
            name, value = j2735.decode(data)
        except Exception:
            self.log.write(mtype, sender, "DROP", "DECODE_FAIL", auth_status=auth,
                           decode_status="INVALID", t_start=t0)
            return
        if name == "MapData":
            if self.map is None:
                self.map = intersection.IntersectionMap(value)
            self.count["MAP"] += 1
            self.log.write("MAP", sender, "ACCEPT", auth_status=auth, t_start=t0)
        elif name == "SPAT":
            self.signals = intersection.spat_states(value)
            self.spat_time = time.monotonic()
            self.count["SPAT"] += 1
            self.log.write("SPAT", sender, "ACCEPT", auth_status=auth, t_start=t0)
        elif name == "PersonalSafetyMessage":
            self.peds[sender] = (j2735.psm_state(value), time.monotonic())
            self.count["PSM"] += 1
            self.log.write("PSM", sender, "ACCEPT", auth_status=auth, t_start=t0)
        elif name == "TravelerInformation":
            key = value.get("packetID", b"").hex() or sender
            paths = self.zones.get(key, (None, 0, set()))[2] | {path}
            self.zones[key] = (j2735.tim_zones(value), time.monotonic(), paths)
            self.count[mtype] += 1
            self.log.write(mtype, sender, "ACCEPT", auth_status=auth, t_start=t0)

    def my_signal(self, state):
        """(차로 정보, 신호 색 'GREEN'/'YELLOW'/'RED'/'UNKNOWN') — 교차로 밖이면 (None, None)"""
        if self.map is None:
            return None, "UNKNOWN"
        loc = self.map.locate(state["lat"], state["lon"], state["heading"])
        if loc is None:
            return None, None
        if self.spat_time is None or time.monotonic() - self.spat_time > SPAT_TIMEOUT:
            return loc, "UNKNOWN"
        sig = self.signals.get(loc["signalGroup"])
        return loc, intersection.color(sig[0]) if sig else "UNKNOWN"


    def ped_alert(self, me):
        """내 앞길 위에 있거나 곧 들어올 보행자 중 가장 가까운 것: (앞 거리 m, 보행자 정보) 또는 None"""
        now, best = time.monotonic(), None
        for pid, (ped, t) in list(self.peds.items()):
            if now - t > PSM_TIMEOUT:
                del self.peds[pid]
                continue
            ahead, right = geo.relative(me["lat"], me["lon"], me["heading"], ped["lat"], ped["lon"])
            if not 0 < ahead < PED_LOOKAHEAD:
                continue
            vx, vy = geo.velocity(ped["speed"], ped["heading"])          # 보행자 속도를 내 기준으로
            h = math.radians(me["heading"])
            v_right = vx * math.cos(h) - vy * math.sin(h)
            future = right + v_right * PED_PREDICT
            on_path = abs(right) < PED_CORRIDOR or abs(future) < PED_CORRIDOR or right * future < 0
            if on_path and (best is None or ahead < best[0]):
                best = (ahead, dict(ped, right=right))
        return best

    def active_zones(self):
        """지금 유효한 공사 구간들 [(구간, 받은 경로들)]"""
        now, out = time.monotonic(), []
        for key, (zones, t, paths) in list(self.zones.items()):
            if now - t > TIM_TIMEOUT:
                del self.zones[key]
                continue
            out += [(z, paths) for z in zones]
        return out


def ped_speed(alert):
    """보행자 앞에서 멈추는 목표 속도"""
    if alert is None:
        return None
    d = alert[0] - PED_GAP
    return 0.0 if d <= 0.5 else math.sqrt(2 * DECEL * d)


def zone_speed(me, zones):
    """공사 구간 안이거나 그쪽으로 가는 중이면 권고 속도까지 줄이는 목표 속도. 상관없으면 None"""
    best = None
    for z, _ in zones:
        if z["speed"] is None:
            continue
        dist = geo.distance_m(me["lat"], me["lon"], z["lat"], z["lon"])
        if dist <= z["radius"]:
            v = z["speed"]
        elif geo.angle_diff(me["heading"], geo.bearing_deg(me["lat"], me["lon"], z["lat"], z["lon"])) < ZONE_ANGLE:
            v = math.sqrt(z["speed"] ** 2 + 2 * ZONE_DECEL * (dist - z["radius"]))
        else:
            continue
        if v < ROAD_SPEED and (best is None or v < best):
            best = v
    return best


def decide_speed(loc, light, speed):
    """협력주행 판단: 목표 속도(m/s)를 돌려준다. None이면 SUMO 기본 주행에 맡김."""
    if loc is None:
        return None                                   # 교차로 접근 중이 아님
    d = loc["dist_to_stop"] - STOP_GAP
    if light == "GREEN":
        return None
    if light == "YELLOW" and d < speed * speed / (2 * DECEL):
        return None                                   # 이미 설 수 없는 거리면 통과
    if light == "UNKNOWN" and d > 60:
        return max(speed - 1.0 * STEP, 5.0)           # 신호를 모르면 천천히 감속
    if d <= 0.5:
        return 0.0
    return min(speed, math.sqrt(2 * DECEL * d))       # 정지선 앞에서 멈추는 속도


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vehicle", required=True, help="SUMO 차량 ID (obu1, obu2)")
    ap.add_argument("--order", type=int, required=True, help="TraCI 클라이언트 순서 (1, 2)")
    ap.add_argument("--port", type=int, default=8813, help="SUMO TraCI 포트")
    ap.add_argument("--coop", action="store_true", help="V2X로 받은 정보만 보고 주행 (협력주행)")
    ap.add_argument("--no-v2n", action="store_true", help="휴대폰망(교통센터) 연결 안 함")
    args = ap.parse_args()

    name = args.vehicle.upper().replace("OBU", "OBU-0")       # obu1 -> OBU-01
    temp_id = args.vehicle.upper().encode()[:4].ljust(4, b"0")
    ident = Identity(name)                                    # SCMS 인증서 준비
    print(f"[{name}] 인증서 받음: PSID {[hex(p) for p in ident.cert.psids]}")
    radio = Radio(name)
    log = V2XLog(name)
    view = V2XView(log, ident.verifier)
    modem = None if args.no_v2n else v2n.V2NClient(name)        # 휴대폰망 모뎀 (교통센터)

    traci.init(port=args.port, label=args.vehicle)
    traci.setOrder(args.order)
    print(f"[{name}] SUMO 연결됨. 협력주행 {'켬' if args.coop else '끔'}")

    seen, msg_cnt, last_line, controlled, v2x_driving = False, 0, None, False, False
    while traci.simulation.getMinExpectedNumber() > 0:
        t0 = time.monotonic()
        traci.simulationStep()
        for wsm in radio.recv_all():
            view.handle(wsm, "V2X")
        if modem:
            for wsm in modem.recv_all():
                view.handle(wsm, "V2N")
        state = read_vehicle(args.vehicle)
        if state:
            if args.coop and not v2x_driving and view.map is not None:
                # MAP을 받은 뒤부터 SUMO 신호등을 보지 않게 함 (안전거리·가감속 한계만 지킴).
                # MAP을 못 받았으면 정지선을 모르므로 SUMO 기본 주행(신호 준수)을 유지한다.
                traci.vehicle.setSpeedMode(args.vehicle, 0b00111)
                v2x_driving = True
                print(f"[{name}] MAP 수신: 이제 V2X 신호만 보고 주행")
            seen = True
            msg_cnt = (msg_cnt + 1) % 128                     # J2735 MsgCount: 0..127 순환
            bsm = j2735.make_bsm(msg_cnt, temp_id, **state)
            signed = wsmp.encode(psid.BSM, ident.sign(bsm, psid.BSM))
            radio.send(signed)                                        # 서명해서 방송 (V2X)
            if modem and msg_cnt % 10 == 0:
                modem.send(signed)                                    # 1초마다 교통센터에 위치 보고 (V2N)

            loc, light = view.my_signal(state)
            alert = view.ped_alert(state)
            zones = view.active_zones()
            targets = [ped_speed(alert), zone_speed(state, zones)] if args.coop else []
            if v2x_driving:
                targets.append(decide_speed(loc, light, state["speed"]))
            targets = [v for v in targets if v is not None]
            target = min(targets) if targets else None
            if args.coop:
                if target is not None:
                    traci.vehicle.setSpeed(args.vehicle, target)
                    controlled = True
                elif controlled:
                    traci.vehicle.setSpeed(args.vehicle, -1)  # 다시 SUMO 기본 주행
                    controlled = False

            where = (f"차로 {loc['laneID']} 정지선까지 {loc['dist_to_stop']:5.1f}m"
                     if loc else "교차로 밖")
            extra = ""
            if alert:
                extra += f" | 보행자 경고: 앞 {alert[0]:4.1f}m 옆 {alert[1]['right']:+4.1f}m"
            for z, paths in zones:
                if geo.distance_m(state["lat"], state["lon"], z["lat"], z["lon"]) <= z["radius"]:
                    extra += f" | 공사 구간 안: 권고 {z['text']} (받은 경로 {'+'.join(sorted(paths))})"
            line = (light, loc is not None, alert is not None, "공사" in extra)   # 상태가 바뀔 때와 1초마다 출력
            if line != last_line or int(traci.simulation.getTime() * 10) % 10 == 0:
                print(f"[{name}] t={traci.simulation.getTime():5.1f}s 속도 {state['speed']:5.2f}m/s | "
                      f"신호 {light or '-':7s} | {where}{extra}"
                      + f" | 받은 SPaT {view.count['SPAT']} MAP {view.count['MAP']} PSM {view.count['PSM']}"
                      + f" TIM {view.count['TIM(V2X)']}/{view.count['TIM(V2N)']}(V2X/V2N)"
                      + (f" | 거부 {view.rejected}" if view.rejected else "")
                      + (f" | 목표속도 {target:.1f}" if target is not None else ""))
            last_line = line
        elif seen:
            print(f"[{name}] 목적지 도착, 종료. 거부한 메시지 {view.rejected}")
            break
        time.sleep(max(0.0, STEP - (time.monotonic() - t0)))

    if modem:
        modem.close()
    traci.close()


if __name__ == "__main__":
    main()
