"""RSU 수신 게이트웨이: 가상 무선에서 받은 BSM을 IEEE 1609.2로 검증하고,
통과한 것만 J2735 MessageFrame으로 꺼내 V2X-Hub MessageReceiver(UDP 26789)로 넘긴다.
(V2X-Hub는 서명을 검증하지 않으므로 이 게이트웨이가 앞에서 걸러야 한다.)

검증: 1 서명  2 권한(PSID)  3 유효기간  4 발급 체인. 실패하면 버리고 기록한다.
사용법: python3 rsu-gateway/gateway.py
"""
import argparse
import os
import socket
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import j2735, psid, sec1609, wsmp  # noqa: E402
from common.identity import trust_store  # noqa: E402
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
    verifier = trust_store()                                  # SCMS 신뢰 목록 = 루트·ICA·ACA
    print(f"[gateway] 가상 무선 수신 -> 1609.2 검증 -> V2X-Hub {args.v2xhub}")

    count, rejected, last_report = {}, {}, time.monotonic()
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
        signer = "?"
        try:
            if not sec1609.is_spdu(data):
                raise sec1609.VerifyError(1, "UNSIGNED")
            data, cert = verifier.verify(data, psid.BSM)
            auth, signer = "VALID", cert.name
        except sec1609.VerifyError as e:
            rejected[e.reason] = rejected.get(e.reason, 0) + 1
            log.write("BSM", signer, "REJECT", e.reason, auth_status="INVALID",
                      fail_step=e.step, t_start=t0)
            continue
        try:
            _, bsm = j2735.decode(data)
            sender = signer if signer != "?" else bsm["coreData"]["id"].decode(errors="replace")
        except Exception:
            log.write("BSM", signer, "DROP", "DECODE_FAIL", auth_status=auth,
                      decode_status="INVALID", t_start=t0)
            continue
        out.sendto(data, (host, int(port)))           # V2X-Hub에는 J2735 MessageFrame만
        log.write("BSM", sender, "ACCEPT", auth_status=auth, t_start=t0)
        count[sender] = count.get(sender, 0) + 1
        if time.monotonic() - last_report > 5:
            print(f"[gateway] V2X-Hub로 전달한 BSM: {count}" + (f", 거부: {rejected}" if rejected else ""))
            last_report = time.monotonic()


if __name__ == "__main__":
    main()
