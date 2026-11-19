"""가상 OBU (2단계-1차): SUMO에서 내 차의 위치·속도·방향을 읽어 0.1초마다 출력한다.

사용법:
    python3 obu/obu.py --vehicle obu1 --order 1
    python3 obu/obu.py --vehicle obu2 --order 2

SUMO는 미리 이렇게 띄워 둔다 (OBU 2대가 함께 붙도록 클라이언트 2개를 기다림):
    sumo-gui -c sumo/intersection.sumocfg --remote-port 8813 --num-clients 2 --start
"""
import argparse
import time

import traci

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
    parser.add_argument("--port", type=int, default=8813)
    args = parser.parse_args()

    traci.init(port=args.port, label=args.vehicle)
    traci.setOrder(args.order)
    print(f"[{args.vehicle}] SUMO 연결됨")

    seen = False
    while traci.simulation.getMinExpectedNumber() > 0:
        t0 = time.monotonic()
        traci.simulationStep()
        state = read_vehicle(args.vehicle)
        if state:
            seen = True
            print(f"[{args.vehicle}] t={traci.simulation.getTime():5.1f}s "
                  f"lat={state['lat']:.7f} lon={state['lon']:.7f} "
                  f"speed={state['speed']:5.2f}m/s heading={state['heading']:6.1f}")
        elif seen:
            print(f"[{args.vehicle}] 목적지 도착, 종료")
            break
        # 실제 시간과 맞추기 (0.1초에 한 스텝)
        time.sleep(max(0.0, STEP - (time.monotonic() - t0)))

    traci.close()


if __name__ == "__main__":
    main()
