"""가상 OBU (2단계): SUMO에서 내 차 상태를 읽어 J2735 BSM을 만들고 0.1초마다 보낸다.

사용법:
    python3 obu/obu.py --vehicle obu1 --order 1
    python3 obu/obu.py --vehicle obu2 --order 2

SUMO는 미리 이렇게 띄워 둔다 (OBU 2대가 함께 붙도록 클라이언트 2개를 기다림):
    sumo-gui -c sumo/intersection.sumocfg --remote-port 8813 --num-clients 2 --start

2단계에서는 BSM을 V2X-Hub MessageReceiver(UDP 26789)로 바로 보낸다.
(5~6단계에서 서명을 붙이고, 가상 무선과 RSU 검증 게이트웨이를 거치도록 바꾼다.)
"""
import argparse
import os
import socket
import sys
import time

import traci

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import j2735  # noqa: E402

STEP = 0.1  # SUMO 한 스텝 = 0.1초 = BSM 10 Hz


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vehicle", required=True, help="SUMO 차량 ID (obu1, obu2)")
    parser.add_argument("--order", type=int, required=True, help="TraCI 클라이언트 순서 (1, 2)")
    parser.add_argument("--port", type=int, default=8813, help="SUMO TraCI 포트")
    parser.add_argument("--dest", default="127.0.0.1:26789",
                        help="BSM을 보낼 곳 (V2X-Hub MessageReceiver)")
    args = parser.parse_args()

    dest_host, dest_port = args.dest.split(":")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # 임시 ID 4바이트: obu1 -> b"OBU1"
    temp_id = args.vehicle.upper().encode()[:4].ljust(4, b"0")

    traci.init(port=args.port, label=args.vehicle)
    traci.setOrder(args.order)
    print(f"[{args.vehicle}] SUMO 연결됨, BSM 전송 대상 {args.dest}")

    seen = False
    msg_cnt = 0
    while traci.simulation.getMinExpectedNumber() > 0:
        t0 = time.monotonic()
        traci.simulationStep()
        state = read_vehicle(args.vehicle)
        if state:
            seen = True
            msg_cnt = (msg_cnt + 1) % 128        # J2735 MsgCount: 0..127 순환
            bsm = j2735.make_bsm(msg_cnt, temp_id, **state)
            sock.sendto(bsm, (dest_host, int(dest_port)))
            print(f"[{args.vehicle}] t={traci.simulation.getTime():5.1f}s "
                  f"lat={state['lat']:.7f} lon={state['lon']:.7f} "
                  f"speed={state['speed']:5.2f}m/s -> BSM {len(bsm)}B #{msg_cnt}")
        elif seen:
            print(f"[{args.vehicle}] 목적지 도착, 종료")
            break
        # 실제 시간과 맞추기 (0.1초에 한 스텝)
        time.sleep(max(0.0, STEP - (time.monotonic() - t0)))

    traci.close()


if __name__ == "__main__":
    main()
