"""RSU 수신 게이트웨이: 가상 무선에서 받은 BSM을 V2X-Hub MessageReceiver(UDP 26789)로 넘긴다.

3단계: 검증 없이 그대로 통과 (6단계에서 1609.2 서명 검증을 이 자리에 넣는다).

사용법: python3 rsu-gateway/gateway.py
"""
import argparse
import os
import socket
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import j2735, psid, wsmp  # noqa: E402
from common.radio import Radio  # noqa: E402
from common.v2xlog import V2XLog  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--v2xhub", default="127.0.0.1:26789", help="V2X-Hub MessageReceiver")
    args = ap.parse_args()
    host, port = args.v2xhub.split(":")
    out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    radio = Radio("RSU-01-gateway")
    log = V2XLog("RSU-01-gateway")
    print(f"[gateway] 가상 무선 수신 -> V2X-Hub {args.v2xhub} (검증 없음)")

    count, last_report = {}, time.monotonic()
    while True:
        wsm = radio.recv(timeout=1.0)
        if wsm is None:
            continue
        t0 = time.perf_counter()
        try:
            p, data = wsmp.decode(wsm)
        except ValueError:
            log.write("UNKNOWN", "?", "DROP", "BAD_WSMP", decode_status="INVALID", t_start=t0)
            continue
        if p != psid.BSM:
            continue                                   # RSU가 받을 메시지는 BSM뿐
        try:
            _, bsm = j2735.decode(data)
            sender = bsm["coreData"]["id"].decode(errors="replace")
        except Exception:
            log.write("BSM", "?", "DROP", "DECODE_FAIL", decode_status="INVALID", t_start=t0)
            continue
        out.sendto(data, (host, int(port)))           # V2X-Hub에는 J2735 MessageFrame만
        log.write("BSM", sender, "ACCEPT", t_start=t0)
        count[sender] = count.get(sender, 0) + 1
        if time.monotonic() - last_report > 5:
            print(f"[gateway] V2X-Hub로 전달한 BSM: {count}")
            last_report = time.monotonic()


if __name__ == "__main__":
    main()
