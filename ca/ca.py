"""CA 서버 (단순화한 SCMS): 루트 CA → 등록 CA(ECA) / 응용 인증서 CA(ACA) 구조.

  1) 장치가 공개키를 보내 '등록 인증서'를 받는다 (/enroll). 등록된 장치 이름만 허용.
  2) 장치가 등록 인증서로 서명한 요청을 보내 '응용 인증서'를 받는다 (/app-cert).
     권한(PSID)은 CA가 장치 종류로 정한다: OBU = BSM, RSU = SPaT·MAP
  3) 누구나 체인(루트·ECA·ACA 인증서)을 받아 신뢰 저장소로 쓴다 (/chain).

인증서는 IEEE 1609.2 명시적 인증서(COER). 통신은 HTTP + JSON(hex) — HTTPS는 2차 보안 과제.
CA 키와 인증서는 ca/data/ 에 저장해 재시작해도 같은 루트를 쓴다 (.gitignore로 제외).

사용법: python3 ca/ca.py [--port 8440]
"""
import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from cryptography.hazmat.primitives.serialization import (Encoding, NoEncryption, PrivateFormat,
                                                          load_pem_private_key)
from cryptography.hazmat.primitives.asymmetric import ec

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import psid, sec1609 as S  # noqa: E402

DATA = os.path.join(os.path.dirname(__file__), "data")
# 등록된 장치와 종류. OBU-99는 7단계 시험용(탈취된 OBU를 가정)
DEVICES = {"RSU-01": "rsu", "OBU-01": "obu", "OBU-02": "obu", "OBU-99": "obu"}
ROLE_PSIDS = {"obu": [psid.BSM], "rsu": [psid.SPAT, psid.MAP]}
YEAR = 365 * 24 * 3600


def _load_or_make(name, issuer=None, duration=YEAR):
    kpath, cpath = os.path.join(DATA, f"{name}.key.pem"), os.path.join(DATA, f"{name}.cert.oer")
    if os.path.exists(kpath) and os.path.exists(cpath):
        key = load_pem_private_key(open(kpath, "rb").read(), None)
        return key, S.Cert(open(cpath, "rb").read())
    key = S.new_key()
    if issuer is None:
        cert = S.issue_cert(name, key.public_key(), key, None, ca=True, duration_s=10 * YEAR)
    else:
        cert = S.issue_cert(name, key.public_key(), issuer[0], issuer[1], ca=True, duration_s=duration)
    open(kpath, "wb").write(key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
    open(cpath, "wb").write(cert.coer)
    print(f"[ca] 새로 만듦: {cert}")
    return key, cert


class CA:
    def __init__(self):
        os.makedirs(DATA, exist_ok=True)
        self.root = _load_or_make("root-ca")
        self.eca = _load_or_make("enrollment-ca", self.root)
        self.aca = _load_or_make("application-ca", self.root)
        self.verifier = S.Verifier(self.root[1], [self.eca[1]])

    def chain(self):
        return {"root": self.root[1].coer.hex(), "eca": self.eca[1].coer.hex(),
                "aca": self.aca[1].coer.hex()}

    def enroll(self, req):
        name = req["name"]
        if name not in DEVICES:
            raise PermissionError(f"등록되지 않은 장치: {name}")
        pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), bytes.fromhex(req["pub"]))
        cert = S.issue_cert(name, pub, self.eca[0], self.eca[1], psids=[psid.CERT_REQUEST],
                            duration_s=YEAR)
        print(f"[ca] 등록 인증서 발급: {name}")
        return {"cert": cert.coer.hex()}

    def app_cert(self, req):
        # 요청은 등록 인증서로 서명된 1609.2 SignedData. 안의 내용은 JSON
        try:
            payload, signer = self.verifier.verify(bytes.fromhex(req["request"]), psid.CERT_REQUEST)
        except S.VerifyError as e:
            raise PermissionError(f"요청 검증 실패: {e.reason}")
        body = json.loads(payload)
        name = body["name"]
        if signer.name != name or name not in DEVICES:
            raise PermissionError("등록 인증서와 요청 장치 이름이 다름")
        pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), bytes.fromhex(body["pub"]))
        duration = max(1, int(body.get("duration_s", 7 * 24 * 3600)))
        psids = ROLE_PSIDS[DEVICES[name]]
        cert = S.issue_cert(name, pub, self.aca[0], self.aca[1], psids=psids, duration_s=duration)
        print(f"[ca] 응용 인증서 발급: {name} PSID {[hex(p) for p in psids]} 유효 {duration}초")
        return {"cert": cert.coer.hex()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8440)
    args = ap.parse_args()
    ca = CA()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/chain":
                return self._send(200, ca.chain())
            self._send(404, {"error": "없는 주소"})

        def do_POST(self):
            try:
                req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                if self.path == "/enroll":
                    return self._send(200, ca.enroll(req))
                if self.path == "/app-cert":
                    return self._send(200, ca.app_cert(req))
                self._send(404, {"error": "없는 주소"})
            except PermissionError as e:
                print(f"[ca] 거부: {e}")
                self._send(403, {"error": str(e)})
            except Exception as e:  # noqa: BLE001
                self._send(400, {"error": f"잘못된 요청: {e}"})

        def log_message(self, *a):
            pass

    print(f"[ca] CA 서버 시작 http://127.0.0.1:{args.port}  루트 {ca.root[1].hashed_id8.hex()}")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
