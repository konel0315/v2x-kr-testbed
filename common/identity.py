"""장치 쪽 인증서 준비: OpenSCMS(IEEE 1609.2.1)에서 등록인증서 → 응용인증서를 받고, 신뢰 목록으로 검증기를 만든다.

실제 장치처럼
  - 루트 인증서는 장치에 미리 넣어 둔다(출고 시 설치). 여기서는 OpenSCMS가 만든 루트 인증서 파일을
    처음 한 번 ee-data/trust/root.cert 로 복사해 둔다.
  - 중간 CA(ICA, ACA) 인증서는 RA에서 받아 루트로 서명을 확인한 뒤에만 믿는다.
"""
import os

from common import psid, scms_client, sec1609 as S

# 장치 이름 → (장치 종류, 요청할 PSID). RA는 장치 종류별로 허용된 PSID만 발급한다.
DEVICES = {
    "OBU-01": ("obu", [psid.BSM]),
    "OBU-02": ("obu", [psid.BSM]),
    "RSU-01": ("rsu", [psid.SPAT, psid.MAP]),
}

OPENSCMS_DIR = os.environ.get("OPENSCMS_DIR", os.path.expanduser("~/openscms/OpenSCMS"))
TRUST_DIR = os.path.join(scms_client.DATA_DIR, "trust")


def _root():
    """장치에 설치된 루트 인증서 (없으면 OpenSCMS 폴더에서 한 번 복사)"""
    path = os.path.join(TRUST_DIR, "root.cert")
    if not os.path.exists(path):
        src = os.path.join(OPENSCMS_DIR, "certs", "rootca", "rootcaCertificate.coer")
        if not os.path.exists(src):
            raise RuntimeError(f"루트 인증서가 없습니다: {src} (OpenSCMS 설치 1-5 단계를 확인하세요)")
        os.makedirs(TRUST_DIR, exist_ok=True)
        with open(src, "rb") as f, open(path, "wb") as g:
            g.write(f.read())
    with open(path, "rb") as f:
        root = S.Cert(f.read())
    if root.role != "root" or not root.signed_by(None):
        raise RuntimeError("루트 인증서가 올바르지 않습니다")
    return root


def trust_store(device="RSU-01"):
    """루트 + RA에서 받은 중간 CA(ICA, ACA)로 검증기를 만든다.
    device의 응용인증서 발급 사슬을 RA에서 받아, 루트부터 차례로 서명을 확인한 것만 믿는다."""
    store = scms_client.Store(device)
    if not store.has("app.cert"):
        raise RuntimeError(f"{device} 인증서가 아직 없습니다. 먼저 python3 scripts/provision.py 를 실행하세요.")
    return _verifier(store.read("app.cert"))


def _verifier(leaf):
    root = _root()
    inter = []
    for c in reversed(scms_client.fetch_chain(leaf)):    # 루트 쪽부터 차례로 확인
        cert = S.Cert(c)
        if cert.hashed_id8 == root.hashed_id8:
            continue
        issuer = root if cert.issuer[1] == root.hashed_id8 else next(
            (i for i in inter if i.hashed_id8 == cert.issuer[1]), None)
        if issuer is None or not cert.is_ca or not cert.signed_by(issuer):
            raise RuntimeError(f"RA에서 받은 CA 인증서를 믿을 수 없습니다: {cert}")
        inter.append(cert)
    return S.Verifier(root, inter)


class Identity:
    """한 장치의 키와 응용인증서 (OpenSCMS에서 발급)"""

    def __init__(self, name):
        if name not in DEVICES:
            raise ValueError(f"등록되지 않은 장치 이름: {name}")
        device_type, psids = DEVICES[name]
        self.name = name
        r = scms_client.provision(name, device_type, psids, log=print)
        self.key = r["app_key"]
        self.cert = S.Cert(r["app_cert"])
        missing = [hex(p) for p in psids if p not in self.cert.psids]
        if missing:
            raise RuntimeError(f"[{name}] 응용인증서에 PSID {missing} 권한이 없습니다. "
                               "OpenSCMS 수정본(openscms-patch)이 적용됐는지 확인하세요.")
        self.verifier = _verifier(r["app_cert"])

    def sign(self, payload, p):
        return S.sign_data(payload, p, self.key, self.cert)
