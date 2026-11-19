"""가상 OBU: SUMO 차량에 달린 단말기.

  - 시작: CA에서 인증서를 받는다 (BSM 권한)
  - 보내기: 내 차 상태로 J2735 BSM을 만들어 IEEE 1609.2로 서명하고 0.1초마다 방송
  - 받기:   RSU가 방송한 SPaT(신호)·MAP(교차로 지도)을 검증한 뒤, 통과한 것만 쓴다
            검증: 1 서명  2 권한(PSID)  3 유효기간  4 발급 체인
  - 협력주행(--coop): SUMO 신호등은 무시하고, V2X로 받은 신호만 보고 정지·출발

사용법 (CA 서버와 SUMO(--num-clients 3)를 미리 실행. 3번째 클라이언트는 tsc):
    python3 obu/obu.py --vehicle obu1 --order 1 [--coop] [--no-verify]
    --no-verify: 검증을 끈다 (7단계 '가짜 신호' 시험의 비교용)
"""
import argparse
import math
import os
import sys
import time

import traci

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import intersection, j2735, psid, sec1609, wsmp  # noqa: E402
from common.identity import Identity  # noqa: E402
from common.radio import Radio  # noqa: E402
from common.v2xlog import V2XLog  # noqa: E402

STEP = 0.1              # SUMO 한 스텝 = 0.1초 = BSM 10 Hz
DECEL = 3.0             # 정지할 때 쓸 감속도 (m/s^2)
STOP_GAP = 2.0          # 정지선 몇 m 앞에서 설지
SPAT_TIMEOUT = 1.0      # SPaT를 이 시간 넘게 못 받으면 신호를 모른다고 보고 감속


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
        self.verifier = verifier   # None이면 검증 끔
        self.count = {"SPAT": 0, "MAP": 0}
        self.rejected = {}         # 거부 이유 -> 개수

    def _reject(self, mtype, sender, reason, step, t0):
        self.rejected[reason] = self.rejected.get(reason, 0) + 1
        self.log.write(mtype, sender, "REJECT", reason, auth_status="INVALID",
                       fail_step=step, t_start=t0)

    def handle(self, wsm):
        t0 = time.perf_counter()
        try:
            p, data = wsmp.decode(wsm)
        except ValueError:
            return
        if p not in (psid.SPAT, psid.MAP):
            return                                    # 다른 차의 BSM 등은 여기서 안 씀
        mtype, sender, auth = psid.NAMES[p], "?", "NOT_CHECKED"
        # ---- 1609.2 검증: 통과한 것만 쓴다
        if self.verifier is not None:
            if not sec1609.is_spdu(data):
                return self._reject(mtype, sender, "UNSIGNED", 1, t0)
            try:
                data, cert = self.verifier.verify(data, p)
            except sec1609.VerifyError as e:
                return self._reject(mtype, sender, e.reason, e.step, t0)
            sender, auth = cert.name, "VALID"
        elif sec1609.is_spdu(data):
            data = sec1609.unwrap_unverified(data)    # 검증 끔: 내용만 꺼내 그대로 믿음
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
    ap.add_argument("--coop", action="store_true", help="V2X 신호만 보고 주행 (3-1단계)")
    ap.add_argument("--no-verify", action="store_true", help="받은 메시지 검증을 끔 (시험 비교용)")
    args = ap.parse_args()

    name = args.vehicle.upper().replace("OBU", "OBU-0")       # obu1 -> OBU-01
    temp_id = args.vehicle.upper().encode()[:4].ljust(4, b"0")
    ident = Identity(name)                                    # CA에서 인증서 받기
    print(f"[{name}] 인증서 받음: PSID {[hex(p) for p in ident.cert.psids]}, "
          f"검증 {'끔' if args.no_verify else '켬'}")
    radio = Radio(name)
    log = V2XLog(name)
    view = V2XView(log, None if args.no_verify else ident.verifier)

    traci.init(port=args.port, label=args.vehicle)
    traci.setOrder(args.order)
    print(f"[{name}] SUMO 연결됨. 협력주행 {'켬' if args.coop else '끔'}")

    seen, msg_cnt, last_line, controlled, v2x_driving = False, 0, None, False, False
    last_tls, violations = None, 0
    while traci.simulation.getMinExpectedNumber() > 0:
        t0 = time.monotonic()
        traci.simulationStep()
        for wsm in radio.recv_all():
            view.handle(wsm)
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
            radio.send(wsmp.encode(psid.BSM, ident.sign(bsm, psid.BSM)))   # 서명해서 방송

            loc, light = view.my_signal(state)
            target = decide_speed(loc, light, state["speed"]) if v2x_driving else None
            if v2x_driving:
                if target is not None:
                    traci.vehicle.setSpeed(args.vehicle, target)
                    controlled = True
                elif controlled:
                    traci.vehicle.setSpeed(args.vehicle, -1)  # 다시 SUMO 기본 주행
                    controlled = False

            # 신호 위반 감지: 정지선을 넘는 순간 SUMO의 실제 신호가 빨강이었는가
            nxt = traci.vehicle.getNextTLS(args.vehicle)
            if nxt:
                last_tls = nxt[0]
            elif last_tls is not None:
                if last_tls[3] in "rRyY" and last_tls[2] < 5:
                    violations += 1
                    print(f"[{name}] !!! 신호 위반: 실제 신호 '{last_tls[3]}'에서 교차로 진입 "
                          f"(V2X로 본 신호 {light})")
                    log.write("EVENT", name, "RED_LIGHT_VIOLATION", reason=f"actual={last_tls[3]}")
                last_tls = None
            where = (f"차로 {loc['laneID']} 정지선까지 {loc['dist_to_stop']:5.1f}m"
                     if loc else "교차로 밖")
            line = f"신호 {light or '-':7s} | {where}"
            if line.split('|')[0] != (last_line or '|').split('|')[0] or int(traci.simulation.getTime() * 10) % 10 == 0:
                print(f"[{name}] t={traci.simulation.getTime():5.1f}s 속도 {state['speed']:5.2f}m/s | "
                      f"{line} | 받은 SPaT {view.count['SPAT']} MAP {view.count['MAP']}"
                      + (f" | 거부 {view.rejected}" if view.rejected else "")
                      + (f" | 목표속도 {target:.1f}" if target is not None else ""))
            last_line = line
        elif seen:
            print(f"[{name}] 목적지 도착, 종료. 신호 위반 {violations}회, 거부한 메시지 {view.rejected}")
            break
        time.sleep(max(0.0, STEP - (time.monotonic() - t0)))

    traci.close()


if __name__ == "__main__":
    main()
