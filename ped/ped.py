"""가상 보행자 단말(스마트폰 앱): SUMO 보행자 한 명을 움직이고, 그 위치로 PSM을 보낸다 (V2P).

  - 시작: OpenSCMS에서 받은 PED-01 응용인증서를 쓴다 (권한 PSM, PSID 0x27)
  - 보내기: 0.1초마다 내 위치·속도·방향으로 J2735 PSM(KS R 1600-6)을 만들어
            IEEE 1609.2로 서명하고 가상 무선으로 방송한다 (단말이 직접 보내는 방식)
  - 각본: 교차로 동쪽 40 m 지점에서 횡단보도가 아닌 곳으로 도로를 건넌다(무단횡단).
          서→동 차(obu1)가 초록불에 교차로를 지나 다가오는 시각에 맞췄다.
  - SUMO 화면에는 노란 점(POI)으로 보인다. SUMO의 차는 POI를 보지 못하므로
    "운전자 눈에 안 보이는 보행자(건물·주차차량에 가려짐)" 상황이 된다.
    차가 서는 것은 오직 V2P 메시지(PSM) 덕분이다. 협력주행을 끄면 차는 그냥 지나가고,
    차가 2 m 안으로 지나가면 '위험'을 기록한다.

사용법 (SUMO --num-clients 4 의 4번째 클라이언트):
    python3 ped/ped.py --order 4 [--start 10] [--no-cross]
"""
import argparse
import math
import os
import sys
import time

import traci

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import j2735, psid, wsmp  # noqa: E402
from common.identity import Identity  # noqa: E402
from common.radio import Radio  # noqa: E402

STEP = 0.1
WALK = 1.3                 # 보행 속도 (m/s)
CROSS_EDGE = "C2E"         # 건너는 도로 (교차로 동쪽)
CROSS_POS = 33.0           # 그 도로 시작점에서 몇 m 지점 (교차로 중심에서 약 40 m)
NORTH_SIDE = 9.0           # 출발점: 도로(동쪽 방향 차로) 중심에서 북쪽으로 몇 m
SOUTH_SIDE = 6.0           # 도착점: 남쪽으로 몇 m
END_TIME = 70.0            # 이 시각에 보행자를 없앤다
DANGER = 2.0               # 차가 이 거리(m) 안으로 지나가면 위험으로 기록


def cross_geometry():
    """건널 지점의 SUMO 좌표: (출발점, 도착점, 도로 방향 단위벡터)"""
    shape = traci.lane.getShape(CROSS_EDGE + "_0")
    (x0, y0), (x1, y1) = shape[0], shape[-1]
    length = math.hypot(x1 - x0, y1 - y0)
    ux, uy = (x1 - x0) / length, (y1 - y0) / length        # 도로 진행 방향 (동쪽)
    nx, ny = -uy, ux                                         # 왼쪽(북쪽) 방향
    cx, cy = x0 + ux * CROSS_POS, y0 + uy * CROSS_POS
    start = (cx + nx * NORTH_SIDE, cy + ny * NORTH_SIDE)
    end = (cx - nx * SOUTH_SIDE, cy - ny * SOUTH_SIDE)
    return start, end, (ux, uy)


def sumo_angle(dx, dy):
    """SUMO 각도 (북 0도, 시계 방향)"""
    return math.degrees(math.atan2(dx, dy)) % 360


class Walker:
    """정해진 각본대로 걷는 보행자: 기다림 -> 도로 건너기 -> 남쪽 보도를 따라 동쪽으로"""

    def __init__(self, start_time, cross):
        self.start_time = start_time
        self.cross = cross
        self.p0, self.p1, self.u = cross_geometry()
        self.cross_len = math.hypot(self.p1[0] - self.p0[0], self.p1[1] - self.p0[1])

    def at(self, t):
        """시각 t의 (x, y, 속도, 방향)"""
        (x0, y0), (x1, y1), (ux, uy) = self.p0, self.p1, self.u
        if not self.cross or t < self.start_time:
            return x0, y0, 0.0, sumo_angle(x1 - x0, y1 - y0)
        d = WALK * (t - self.start_time)
        if d <= self.cross_len:
            k = d / self.cross_len
            return x0 + (x1 - x0) * k, y0 + (y1 - y0) * k, WALK, sumo_angle(x1 - x0, y1 - y0)
        e = d - self.cross_len                                # 다 건넌 뒤 보도를 따라 걷기
        return x1 + ux * e, y1 + uy * e, WALK, sumo_angle(ux, uy)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--order", type=int, default=4, help="TraCI 클라이언트 순서")
    ap.add_argument("--port", type=int, default=8813)
    ap.add_argument("--start", type=float, default=10.0, help="길을 건너기 시작하는 시뮬레이션 시각(초)")
    ap.add_argument("--no-cross", action="store_true", help="건너지 않고 보도에 서 있기")
    args = ap.parse_args()

    ident = Identity("PED-01")                                 # SCMS 인증서 준비 (PSM 권한)
    print(f"[PED-01] 인증서 받음: PSID {[hex(p) for p in ident.cert.psids]}")
    radio = Radio("PED-01")
    temp_id = b"PED1"

    traci.init(port=args.port, label="ped")
    traci.setOrder(args.order)
    walker = Walker(args.start, not args.no_cross)
    x, y, _, ang = walker.at(0)
    traci.poi.add("ped1", x, y, (255, 200, 0, 255), poiType="pedestrian", layer=20, width=1.6, height=1.6)
    print(f"[PED-01] SUMO 연결됨. {args.start:.0f}초에 교차로 동쪽 도로를 건넌다 "
          f"({'무단횡단' if not args.no_cross else '건너지 않음'})")

    msg_cnt, last_print, phase, present, danger = 0, -1, None, True, set()
    while traci.simulation.getMinExpectedNumber() > 0:
        t0 = time.monotonic()
        traci.simulationStep()
        t = traci.simulation.getTime()
        if not present:
            continue
        if t >= END_TIME:
            traci.poi.remove("ped1")
            present = False
            print(f"[PED-01] t={t:5.1f}s 퇴장")
            continue
        x, y, speed, ang = walker.at(t)
        traci.poi.setPosition("ped1", x, y)
        for vid in traci.vehicle.getIDList():                  # 차가 아주 가까이 지나갔는지
            vx, vy = traci.vehicle.getPosition(vid)
            if math.hypot(vx - x, vy - y) < DANGER and vid not in danger:
                danger.add(vid)
                print(f"[PED-01] t={t:5.1f}s 위험! {vid}가 {math.hypot(vx - x, vy - y):.1f}m 거리로 지나감 "
                      f"(속도 {traci.vehicle.getSpeed(vid):.1f}m/s)")
        lon, lat = traci.simulation.convertGeo(x, y)
        msg_cnt = (msg_cnt + 1) % 128
        psm = j2735.make_psm(msg_cnt, temp_id, lat, lon, speed, ang)
        radio.send(wsmp.encode(psid.PSM, ident.sign(psm, psid.PSM)))   # 서명해서 방송

        now_phase = "대기" if speed == 0 else ("건너는 중" if t < args.start + walker.cross_len / WALK else "보도 보행")
        if now_phase != phase or int(t) != last_print and int(t) % 5 == 0:
            print(f"[PED-01] t={t:5.1f}s {now_phase:5s} | 위치 {lat:.6f}, {lon:.6f} | "
                  f"속도 {speed:.1f}m/s 방향 {ang:5.1f}도 | PSM {msg_cnt}")
            phase, last_print = now_phase, int(t)
        time.sleep(max(0.0, STEP - (time.monotonic() - t0)))
    traci.close()


if __name__ == "__main__":
    main()
