"""OBU 2대와 RSU 1대가 OpenSCMS에서 인증서를 받는다 (IEEE 1609.2.1).

순서: 장치 등록(DCM) → 등록인증서(ECA) → 응용인증서 요청(RA, 암호화) → 다운로드(RA)
이미 받은 인증서가 유효하면 다시 받지 않는다. 키와 인증서는 ee-data/ 에 저장한다.
사용법: python3 scripts/provision.py [--renew | --reset]
  --renew : 응용인증서만 새로 받는다
  --reset : 장치 키·인증서를 모두 지우고 등록부터 다시 한다 (OpenSCMS를 새로 설치했을 때)
"""
import argparse
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import identity, scms_client  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--renew", action="store_true", help="응용인증서를 새로 받는다 (등록은 유지)")
    ap.add_argument("--reset", action="store_true", help="장치 키·인증서를 모두 지우고 처음부터")
    args = ap.parse_args()
    if args.reset:
        shutil.rmtree(scms_client.DATA_DIR, ignore_errors=True)
        print(f"{scms_client.DATA_DIR} 를 지웠습니다. 등록부터 다시 합니다.")
    for name in identity.DEVICES:
        if args.renew:
            st = scms_client.Store(name)
            for f in ("app.cert", "app.key", "app-request.hash"):
                if st.has(f):
                    os.remove(st.path(f))
        try:
            ident = identity.Identity(name)
        except (scms_client.ScmsError, RuntimeError) as e:
            print(f"[{name}] 실패: {e}")
            sys.exit(1)
        c = ident.cert
        print(f"[{name}] 준비 완료: 인증서 {c.name}, PSID {[hex(p) for p in c.psids]}, "
              f"발급자 {c.issuer[1].hex()}")
    v = identity.trust_store()
    print("신뢰 목록:", ", ".join(f"{c.role}({h.hex()})" for h, c in v.ca.items()))


if __name__ == "__main__":
    main()
