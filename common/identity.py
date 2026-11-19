"""장치 쪽 인증서 준비: CA에서 등록 인증서 → 응용 인증서를 받고, 체인으로 검증기를 만든다."""
import json
import urllib.request

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from common import psid, sec1609 as S

CA_URL = "http://127.0.0.1:8440"


def _call(url, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"CA 거부: {json.loads(e.read()).get('error')}") from None


def _pub_hex(key):
    return key.public_key().public_bytes(Encoding.X962, PublicFormat.CompressedPoint).hex()


def trust_store(ca_url=CA_URL):
    """CA 체인을 받아 검증기를 만든다. (실제로는 루트 인증서를 장치에 미리 넣어 둔다)"""
    ch = _call(f"{ca_url}/chain")
    return S.Verifier(S.Cert(bytes.fromhex(ch["root"])),
                      [S.Cert(bytes.fromhex(ch["eca"])), S.Cert(bytes.fromhex(ch["aca"]))])


class Identity:
    """한 장치의 키와 응용 인증서"""

    def __init__(self, name, ca_url=CA_URL, duration_s=None):
        self.name = name
        enroll_key = S.new_key()
        ecert = S.Cert(bytes.fromhex(_call(f"{ca_url}/enroll",
                                           {"name": name, "pub": _pub_hex(enroll_key)})["cert"]))
        self.key = S.new_key()
        body = {"name": name, "pub": _pub_hex(self.key)}
        if duration_s:
            body["duration_s"] = duration_s
        request = S.sign_data(json.dumps(body).encode(), psid.CERT_REQUEST, enroll_key, ecert)
        self.cert = S.Cert(bytes.fromhex(_call(f"{ca_url}/app-cert",
                                               {"request": request.hex()})["cert"]))
        self.verifier = trust_store(ca_url)

    def sign(self, payload, p):
        return S.sign_data(payload, p, self.key, self.cert)
