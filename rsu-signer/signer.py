"""RSU 송신 서명기: V2X-Hub ImmediateForward 출력(RSU 4.1 형식, UDP 1516)을 받아
IEEE 1609.2로 서명하고 WSMP로 감싸 가상 무선으로 방송한다.
(V2X-Hub는 서명하지 않으므로 이 서명기가 뒤에서 서명한다.)

인증서는 OpenSCMS(SCMS)에서 받은 RSU-01 응용인증서를 쓴다 (권한 SPaT·MAP).

교통센터가 이미 서명해서 넘긴 메시지(UDP 1517, 예: 공사 안내 TIM)는 다시 서명하지 않는다.
서명을 확인한 뒤 그대로 방송한다 (하이브리드 V2X + V2N: 같은 메시지를 두 경로로).

V2X-Hub ImmediateForward 설정에서 address를 host.docker.internal, port를 1516으로 둔다.
사용법: python3 rsu-signer/signer.py
"""
import argparse
import os
import select
import socket
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import psid, sec1609, wsmp  # noqa: E402
from common.identity import Identity  # noqa: E402
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


FORWARD_PSIDS = (psid.TIM,)      # 센터가 서명해 넘길 수 있는 메시지


def forward_signed(fwd, ident, radio, log, count):
    """교통센터가 서명한 WSM: 서명을 확인하고 그대로 방송 (다시 서명하지 않음)"""
    wsm, _ = fwd.recvfrom(65535)
    t0 = time.perf_counter()
    try:
        p, data = wsmp.decode(wsm)
        if p not in FORWARD_PSIDS:
            raise sec1609.VerifyError(2, "NO_PERMISSION")
        _, cert = ident.verifier.verify(data, p)
    except ValueError:
        log.write("UNKNOWN", "?", "DROP", "BAD_WSMP", decode_status="INVALID", t_start=t0)
        return
    except sec1609.VerifyError as e:
        log.write("FORWARD", "?", "REJECT", e.reason, auth_status="INVALID", fail_step=e.step, t_start=t0)
        return
    radio.send(wsm)
    mtype = psid.NAMES.get(p, "?") + "(센터)"
    log.write(mtype, cert.name, "FORWARDED", auth_status="VALID", t_start=t0)
    count[mtype] = count.get(mtype, 0) + 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", type=int, default=1516, help="ImmediateForward 수신 포트")
    ap.add_argument("--forward", type=int, default=1517, help="교통센터가 서명한 메시지 수신 포트")
    args = ap.parse_args()
    ident = Identity("RSU-01")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", args.listen))
    fwd = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    fwd.bind(("127.0.0.1", args.forward))
    radio = Radio("RSU-01-signer")
    log = V2XLog("RSU-01-signer")
    print(f"[signer] V2X-Hub ImmediateForward(UDP {args.listen}) -> 1609.2 서명 -> 가상 무선 방송. "
          f"인증서 PSID {[hex(p) for p in ident.cert.psids]}, 유효 {int(ident.cert.end - ident.cert.start)}초")

    count, last_report = {}, time.monotonic()
    while True:
        ready, _, _ = select.select([sock, fwd], [], [], 1.0)
        if fwd in ready:
            forward_signed(fwd, ident, radio, log, count)
        if sock not in ready:
            continue
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
        radio.send(wsmp.encode(p, ident.sign(payload, p)))       # 서명해서 방송
        log.write(mtype, "RSU-01", "SENT", auth_status="SIGNED", t_start=t0)
        count[mtype] = count.get(mtype, 0) + 1
        if time.monotonic() - last_report > 5:
            print(f"[signer] 방송한 메시지: {count}")
            last_report = time.monotonic()


if __name__ == "__main__":
    main()
