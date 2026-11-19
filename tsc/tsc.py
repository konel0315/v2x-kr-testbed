"""가상 신호제어기: SUMO 신호등 상태를 NTCIP 1202 TSCBM(신호제어기 방송 메시지)으로 만들어
V2X-Hub SPaT 플러그인(UDP 6053)에 0.1초마다 보낸다. V2X-Hub는 이걸로 J2735 SPaT를 만든다.

사용법 (SUMO에 세 번째 클라이언트로 붙음):
    python3 tsc/tsc.py --order 3

신호 그룹(= NTCIP 페이즈 번호): 서→동 2, 남→북 4, 동→서 6, 북→남 8
"""
import argparse
import socket
import struct
import time

import traci

TLS_ID = "C"
# 진입 도로 -> 페이즈 번호 (tsc/make_map.py의 신호 그룹과 같아야 함)
APPROACH_PHASE = {"W2C": 2, "S2C": 4, "E2C": 6, "N2C": 8}
STRAIGHT_OUT = {"W2C": "C2E", "S2C": "C2N", "E2C": "C2W", "N2C": "C2S"}
STEP = 0.1


def kind(ch):
    """SUMO 신호 문자 -> 'G'(초록) / 'Y'(노랑) / 'R'(빨강)"""
    if ch in "Gg":
        return "G"
    if ch in "yY":
        return "Y"
    return "R"


def straight_link_index():
    """페이즈마다 '직진' 연결이 SUMO 신호 문자열의 몇 번째 글자인지 찾는다."""
    idx = {}
    for i, links in enumerate(traci.trafficlight.getControlledLinks(TLS_ID)):
        for in_lane, out_lane, _via in links:
            ein, eout = in_lane.rsplit("_", 1)[0], out_lane.rsplit("_", 1)[0]
            if ein in APPROACH_PHASE and STRAIGHT_OUT[ein] == eout:
                idx[APPROACH_PHASE[ein]] = i
    return idx


def time_to_change(link_index):
    """지금 신호(초록/노랑/빨강)가 바뀔 때까지 남은 시간(초)."""
    logic = [l for l in traci.trafficlight.getAllProgramLogics(TLS_ID)
             if l.programID == traci.trafficlight.getProgram(TLS_ID)][0]
    phases = logic.phases
    cur = traci.trafficlight.getPhase(TLS_ID)
    now = traci.simulation.getTime()
    remain = traci.trafficlight.getNextSwitch(TLS_ID) - now
    k = kind(phases[cur].state[link_index])
    for step in range(1, len(phases) + 1):
        ph = phases[(cur + step) % len(phases)]
        if kind(ph.state[link_index]) != k:
            return max(0.0, remain)
        remain += ph.duration
    return max(0.0, remain)


def make_tscbm(phase_info, seq):
    """phase_info: {페이즈: ('G'|'Y'|'R', 남은초)} -> TSCBM 바이트 (241B, 빅엔디언)"""
    out = bytearray([0xCD, 16])
    reds = yellows = greens = 0
    for p in range(1, 17):
        if p in phase_info:
            st, remain = phase_info[p]
            t = min(int(remain * 10), 65534)      # 0.1초 단위
            out += struct.pack(">B6H", p, t, t, 0, 0, 0, 0)
            bit = 1 << (p - 1)
            if st == "G":
                greens |= bit
            elif st == "Y":
                yellows |= bit
            else:
                reds |= bit
        else:
            out += struct.pack(">B6H", 0, 0, 0, 0, 0, 0, 0)   # 안 쓰는 페이즈
    out += struct.pack(">11H", reds, yellows, greens, 0, 0, 0, 0, 0, 0, 0, 0)
    tm = time.gmtime()
    ms = int(time.time() * 1000) % 1000
    out += struct.pack(">BBBBBBBH", 0, 0, 0, seq % 256, tm.tm_hour, tm.tm_min, tm.tm_sec, ms)
    return bytes(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--order", type=int, default=3, help="TraCI 클라이언트 순서")
    ap.add_argument("--port", type=int, default=8813)
    ap.add_argument("--dest", default="127.0.0.1:6053", help="V2X-Hub SPaT 플러그인")
    args = ap.parse_args()
    host, port = args.dest.split(":")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    traci.init(port=args.port, label="tsc")
    traci.setOrder(args.order)
    links = straight_link_index()
    print(f"[tsc] SUMO 연결됨. 페이즈 -> 신호 문자 위치: {links}, TSCBM -> {args.dest}")

    seq, last = 0, None
    while traci.simulation.getMinExpectedNumber() > 0:
        t0 = time.monotonic()
        traci.simulationStep()
        state = traci.trafficlight.getRedYellowGreenState(TLS_ID)
        info = {p: (kind(state[i]), time_to_change(i)) for p, i in links.items()}
        sock.sendto(make_tscbm(info, seq), (host, int(port)))
        seq += 1
        summary = " ".join(f"P{p}:{s}" for p, (s, _) in sorted(info.items()))
        if summary != last:
            print(f"[tsc] t={traci.simulation.getTime():5.1f}s {summary} "
                  f"(남은 시간 " + ", ".join(f"P{p} {r:.1f}s" for p, (_, r) in sorted(info.items())) + ")")
            last = summary
        time.sleep(max(0.0, STEP - (time.monotonic() - t0)))
    traci.close()


if __name__ == "__main__":
    main()
