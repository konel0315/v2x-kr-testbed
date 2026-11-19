"""RSU 송신부: V2X-Hub ImmediateForward 출력(RSU 4.1 형식, UDP 1516)을 받아
WSMP로 감싸 가상 무선으로 방송한다.

3단계: 서명 없이 방송 (5단계에서 1609.2 서명을 이 자리에 넣는다).

V2X-Hub ImmediateForward 설정에서 address를 host.docker.internal, port를 1516으로 둔다.
사용법: python3 rsu-signer/signer.py
"""
import argparse
import os
import socket
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import psid, wsmp  # noqa: E402
from common.radio import Radio  # noqa: E402
from common.v2xlog import V2XLog  # noqa: E402


def parse_rsu41(text):
    """'Key=Value' 줄 묶음 -> dict"""
    out = {}
    for line in text.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", type=int, default=1516, help="ImmediateForward 수신 포트")
    args = ap.parse_args()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", args.listen))
    radio = Radio("RSU-01-signer")
    log = V2XLog("RSU-01-signer")
    print(f"[signer] V2X-Hub ImmediateForward(UDP {args.listen}) -> 가상 무선 방송 (서명 없음)")

    count, last_report = {}, time.monotonic()
    while True:
        raw, _ = sock.recvfrom(65535)
        t0 = time.perf_counter()
        msg = parse_rsu41(raw.decode(errors="replace"))
        try:
            p = int(msg["PSID"], 16)
            payload = bytes.fromhex(msg["Payload"])
        except (KeyError, ValueError):
            log.write("UNKNOWN", "V2X-Hub", "DROP", "BAD_RSU41", decode_status="INVALID", t_start=t0)
            continue
        mtype = msg.get("Type", psid.NAMES.get(p, "?"))
        if mtype == "MAP":
            p = psid.MAP          # ImmediateForward 기본 설정은 MAP도 0x8002라서 바로잡음
        if not payload[:2] in (b"\x00\x12", b"\x00\x13"):
            print(f"[signer] 경고: Payload가 J2735 MessageFrame이 아님 ({payload[:4].hex()})")
        radio.send(wsmp.encode(p, payload))
        log.write(mtype, "RSU-01", "SENT", t_start=t0)
        count[mtype] = count.get(mtype, 0) + 1
        if time.monotonic() - last_report > 5:
            print(f"[signer] 방송한 메시지: {count}")
            last_report = time.monotonic()


if __name__ == "__main__":
    main()
