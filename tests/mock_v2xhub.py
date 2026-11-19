"""V2X-Hub 흉내 (V2X-Hub 없이 RSU·OBU 코드를 시험할 때만 사용).

  UDP 6053 TSCBM 수신 -> J2735 SPaT 생성 -> RSU 4.1 형식으로 UDP 1516 전송 (SPaT 플러그인 + ImmediateForward 역할)
  MAP 파일을 1초마다 RSU 4.1 형식으로 1516 전송 (MapPlugin + ImmediateForward 역할)
  UDP 26789 BSM 수신 개수 집계 (MessageReceiver 역할)

사용법: python3 tests/mock_v2xhub.py --map /tmp/map/pangyo_map.txt
"""
import argparse
import os
import select
import socket
import struct
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import j2735  # noqa: E402

STATE = {"G": "protected-Movement-Allowed", "Y": "protected-clearance", "R": "stop-And-Remain"}


def rsu41(mtype, psid, payload):
    return (f"Version=0.7\nType={mtype}\nPSID={psid}\nPriority=7\nTxMode=CONT\nTxChannel=183\n"
            f"TxInterval=0\nDeliveryStart=\nDeliveryStop=\nSignature=False\nEncryption=False\n"
            f"Payload={payload.hex().upper()}\n").encode()


def tscbm_to_spat(b):
    states = {}
    reds, yellows, greens = struct.unpack(">3H", b[210:216])
    for i in range(16):
        pn, tmin = struct.unpack(">BH", b[2 + 13 * i:5 + 13 * i])
        if pn == 0:
            continue
        bit = 1 << (pn - 1)
        st = "G" if greens & bit else "Y" if yellows & bit else "R"
        states[pn] = (STATE[st], tmin / 10)
    return j2735.make_spat(1, states, name="Intersection")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", required=True)
    args = ap.parse_args()
    map_frame = bytes.fromhex(open(args.map).read().strip())
    tsc = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); tsc.bind(("127.0.0.1", 6053))
    mr = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); mr.bind(("127.0.0.1", 26789))
    out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    bsm, spat, last_map, last_rep = {}, 0, 0, time.monotonic()
    print("[mock] V2X-Hub 흉내 시작")
    while True:
        r, _, _ = select.select([tsc, mr], [], [], 0.1)
        if tsc in r:
            b, _ = tsc.recvfrom(4096)
            out.sendto(rsu41("SPAT", "0x8002", tscbm_to_spat(b)), ("127.0.0.1", 1516)); spat += 1
        if mr in r:
            d, _ = mr.recvfrom(4096)
            _, v = j2735.decode(d); k = v["coreData"]["id"].decode()
            bsm[k] = bsm.get(k, 0) + 1
        if time.monotonic() - last_map > 1:
            out.sendto(rsu41("MAP", "0x8002", map_frame), ("127.0.0.1", 1516)); last_map = time.monotonic()
        if time.monotonic() - last_rep > 5:
            print(f"[mock] 받은 BSM {bsm}, 보낸 SPaT {spat}"); last_rep = time.monotonic()


if __name__ == "__main__":
    main()
