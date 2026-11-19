"""7단계 공격 시뮬레이터: 교차로 전체에 '모든 방향 초록불' 가짜 SPaT를 방송한다.

  --mode unsigned      서명 없이 보냄                         -> 기대: UNSIGNED (검증 1단계)
  --mode tamper        진짜 RSU SPaT를 가로채 초록불로 바꿔 보냄 -> 기대: BAD_SIGNATURE (1단계)
  --mode no-permission 정상 OBU 인증서(BSM 권한)로 SPaT 서명   -> 기대: NO_PERMISSION (2단계)
  --mode unknown-ca    공격자가 만든 자체 CA의 인증서로 서명     -> 기대: UNKNOWN_ISSUER (4단계)
  ('만료'는 RSU 인증서를 짧게 받아 확인: bash scripts/run.sh --coop --rsu-cert 20)

사용법 (run.sh 실행 중, 다른 터미널에서):
    python3 tests/attack.py --mode unsigned [--rate 100] [--duration 60]
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import j2735, psid, sec1609 as S, wsmp  # noqa: E402
from common.identity import Identity  # noqa: E402
from common.radio import Radio  # noqa: E402

GREEN = "protected-Movement-Allowed"


def fake_green():
    return j2735.make_spat(1, {sg: (GREEN, 30.0) for sg in (2, 4, 6, 8)}, name="Intersection")


def tamper(spdu):
    """서명된 진짜 SPaT의 내용만 초록불로 바꾸고 서명은 그대로 둔다."""
    S._DATA.from_coer(spdu)
    v = S._DATA.get_val()
    v["content"][1]["tbsData"]["payload"]["data"]["content"] = ("unsecuredData", fake_green())
    S._DATA.set_val(v)
    return S._DATA.to_coer()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True,
                    choices=["unsigned", "tamper", "no-permission", "unknown-ca"])
    ap.add_argument("--rate", type=float, default=100, help="초당 보낼 개수 (진짜 RSU는 10)")
    ap.add_argument("--duration", type=float, default=60, help="공격 시간(초)")
    args = ap.parse_args()
    radio = Radio(f"ATTACKER-{args.mode}")

    signer = None
    if args.mode == "no-permission":
        ident = Identity("OBU-99")                     # 탈취된 정상 OBU 인증서 (BSM 권한만 있음)
        signer = (ident.key, ident.cert)
    elif args.mode == "unknown-ca":
        ek = S.new_key()                               # 공격자가 직접 만든 루트 CA
        evil_root = S.issue_cert("Root-CA", ek.public_key(), ek, None, ca=True)
        k = S.new_key()
        cert = S.issue_cert("RSU-01", k.public_key(), ek, evil_root, psids=[psid.SPAT, psid.MAP])
        signer = (k, cert)

    print(f"[attack] '{args.mode}' 가짜 초록불 SPaT 방송 시작 (초당 {args.rate}개, {args.duration}초)")
    end, sent, last_real = time.monotonic() + args.duration, 0, None
    while time.monotonic() < end:
        if args.mode == "tamper":
            for wsm in radio.recv_all():               # 진짜 RSU의 SPaT를 엿들음
                try:
                    p, data = wsmp.decode(wsm)
                    if p == psid.SPAT and S.is_spdu(data):
                        last_real = data
                except ValueError:
                    pass
            if last_real is None:
                time.sleep(0.05)
                continue
            payload = tamper(last_real)
        elif args.mode == "unsigned":
            payload = fake_green()
        else:
            payload = S.sign_data(fake_green(), psid.SPAT, *signer)
        radio.send(wsmp.encode(psid.SPAT, payload))
        sent += 1
        time.sleep(1 / args.rate)
    print(f"[attack] 종료: {sent}개 보냄")


if __name__ == "__main__":
    main()
