"""OpenSCMS(IEEE 1609.2.1) 단말(EE) 쪽 클라이언트

실제 OBU/RSU가 인증서를 받는 순서를 그대로 따릅니다.

  0. 등록     RA  POST /dcms/device/na          대표키(canonical key)를 SCMS에 등록 (공장 출고 단계)
  1. 등록인증서 ECA POST /v3/enrollment-certificate  EeEcaCertRequestSpdu   (대표키로 자체 서명)
  2. 응용인증서 RA  POST /v3/authorization-certificate EeRaCertRequestSpdu (등록인증서로 서명 → RA 공개키로 암호화)
  3. 다운로드  RA  GET  /v3/authorization-certificate  헤더에 EeRaDownloadRequestSpdu (서명+암호화), zip 수신

신뢰 목록(루트, ICA, ACA)은 RA의 /v3/ca-certificate 에서 받습니다.
키와 인증서는 ee-data/<장치이름>/ 에 저장합니다(.gitignore 대상).
"""
import base64
import io
import json
import os
import time
import urllib.error
import urllib.request
import zipfile

from common import ieee1609_gen as G
from common import scms_crypto as X

D2 = G.Ieee1609Dot2
D21 = G.Ieee1609Dot2Dot1Protocol

RA_URL = os.environ.get("SCMS_RA_URL", "http://127.0.0.1:8092")
ECA_URL = os.environ.get("SCMS_ECA_URL", "http://127.0.0.1:8091")
DATA_DIR = os.environ.get(
    "SCMS_EE_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ee-data"))

EPOCH_2004 = 1072915200
PSID_SECURITY_MGMT = 35


class ScmsError(Exception):
    pass


def time32(t=None):
    return int((time.time() if t is None else t) - EPOCH_2004)


def hid8(coer):
    return X.sha256(coer)[-8:]


# ------------------------------------------------------------ ASN.1 도우미
def enc(T, val):
    T.set_val(val)
    return T.to_coer()


def dec(T, buf):
    T.from_coer(buf)
    return T.get_val()


def cert_coer(val):
    return enc(D2.Certificate, val)


def tbs_coer(tbs_val):
    return enc(D2.ToBeSignedCertificate, tbs_val)


# ------------------------------------------------------------ HTTP
def _http(method, url, body=None, headers=None, ctype=None):
    h = dict(headers or {})
    if ctype:
        h["Content-Type"] = ctype
    req = urllib.request.Request(url, data=body, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)
    except urllib.error.URLError as e:
        raise ScmsError(f"{url} 연결 실패: {e.reason} (port-forward 창이 켜져 있는지 확인하세요)")


def _ok(status, body, headers, what):
    if status not in (200, 202):
        err = headers.get("Ieee-1609.2.1-Error", "")
        raise ScmsError(f"{what} 실패: HTTP {status} {err} {body[:200]!r}")


# ------------------------------------------------------------ 서명된 데이터(1609.2 SignedData) 풀기
def open_signed(spdu, signer_pub=None):
    """Ieee1609Dot2Data(signedData) → (내용 바이트, 서명자 인증서 COER 또는 None)
    signer_pub이 주어지면 그 키로 서명을 확인합니다."""
    v = dec(D2.Ieee1609Dot2Data, spdu)
    kind, sd = v["content"]
    if kind != "signedData":
        raise ScmsError(f"서명 데이터가 아님: {kind}")
    signer_cert = None
    if sd["signer"][0] == "certificate":
        signer_cert = cert_coer(sd["signer"][1][0])
    if signer_pub is not None:
        tbs = enc(D2.ToBeSignedData, sd["tbsData"])
        if not X.verify(signer_pub, sd["signature"], tbs, signer_cert):
            raise ScmsError("응답 서명이 맞지 않습니다")
    inner = sd["tbsData"]["payload"]["data"]
    return inner["content"][1], signer_cert


def make_signed(payload_coer, key, cert_coer_bytes, psid=PSID_SECURITY_MGMT):
    """ScmsPdu를 담은 1609.2 서명 데이터 (서명자: 인증서)"""
    tbs = {"payload": {"data": {"protocolVersion": 3, "content": ("unsecuredData", payload_coer)}},
           "headerInfo": {"psid": psid}}
    tbs_c = enc(D2.ToBeSignedData, tbs)
    sd = {"hashId": "sha256", "tbsData": tbs,
          "signer": ("certificate", [dec(D2.Certificate, cert_coer_bytes)]),
          "signature": X.sign(key, tbs_c, cert_coer_bytes)}
    return enc(D2.Ieee1609Dot2Data, {"protocolVersion": 3, "content": ("signedData", sd)})


def encrypt_to(plain, recipient_cert):
    """받는 쪽 인증서의 encryptionKey로 암호화 (1609.2 EncryptedData, certRecipInfo)"""
    rv = dec(D2.Certificate, recipient_cert)
    ek = rv["toBeSigned"]["encryptionKey"]["publicKey"]
    pub = X.point_to_pubkey(X.point_from_asn(ek[1]))
    aes = os.urandom(16)
    v_pt, c, t = X.ecies_wrap(aes, pub, X.sha256(recipient_cert))
    nonce, ct = X.ccm_encrypt(aes, plain)
    ed = {"recipients": [("certRecipInfo", {
              "recipientId": hid8(recipient_cert),
              "encKey": ("eciesNistP256", {"v": X.point_to_asn(v_pt), "c": c, "t": t})})],
          "ciphertext": ("aes128ccm", {"nonce": nonce, "ccmCiphertext": ct})}
    return enc(D2.Ieee1609Dot2Data, {"protocolVersion": 3, "content": ("encryptedData", ed)})


def signed_cert_request(scoped, key, signer_cert=None):
    """SignedCertificateRequest: signer_cert가 없으면 자체 서명(self)"""
    tbs_c = enc(D21.ScopedCertificateRequest, scoped)
    sig = X.sign(key, tbs_c, signer_cert)
    signer = ("self", 0) if signer_cert is None else ("certificate", [dec(D2.Certificate, signer_cert)])
    scr = enc(D21.SignedCertificateRequest, {
        "hashAlgorithmId": "sha256", "tbsRequest": scoped, "signer": signer, "signature": sig})
    return enc(D2.Ieee1609Dot2Data, {"protocolVersion": 3, "content": ("signedCertificateRequest", scr)})


# ------------------------------------------------------------ 신뢰 목록
def fetch_ca_cert(hashed_id8_hex, ra_url=RA_URL):
    st, body, h = _http("GET", f"{ra_url}/v3/ca-certificate?certId={hashed_id8_hex}")
    _ok(st, body, h, f"CA 인증서({hashed_id8_hex}) 받기")
    return body


def fetch_ra_cert(ra_url=RA_URL):
    st, body, h = _http("GET", f"{ra_url}/v3/ra-certificate")
    _ok(st, body, h, "RA 인증서 받기")
    return body


def fetch_chain(leaf_coer, ra_url=RA_URL):
    """leaf의 발급자를 따라 루트까지 받아 [발급자, ..., 루트] 순서로 돌려줍니다."""
    chain = []
    cur = leaf_coer
    for _ in range(6):
        iss = dec(D2.Certificate, cur)["issuer"]
        if iss[0] == "self":
            return chain
        parent = fetch_ca_cert(iss[1].hex(), ra_url)
        chain.append(parent)
        cur = parent
    raise ScmsError("인증서 사슬이 너무 깁니다")


# ------------------------------------------------------------ 저장소
class Store:
    def __init__(self, name):
        self.dir = os.path.join(DATA_DIR, name)
        os.makedirs(self.dir, exist_ok=True)
        try:
            os.chmod(self.dir, 0o700)
        except OSError:
            pass

    def path(self, f):
        return os.path.join(self.dir, f)

    def has(self, f):
        return os.path.exists(self.path(f))

    def read(self, f):
        with open(self.path(f), "rb") as fh:
            return fh.read()

    def write(self, f, data, secret=False):
        p = self.path(f)
        with open(p, "wb") as fh:
            fh.write(data)
        if secret:
            os.chmod(p, 0o600)

    def key(self, f):
        """32바이트 비밀키 파일 → 키 (없으면 새로 만듦)"""
        if not self.has(f):
            k = X.new_key()
            self.write(f, X.priv_int(k).to_bytes(32, "big"), secret=True)
            return k
        return X.key_from_int(int.from_bytes(self.read(f), "big"))


# ------------------------------------------------------------ 0. 장치 등록
def register(store, device_type, ra_url=RA_URL):
    """대표키를 RA(DCM)에 등록합니다. 이미 등록돼 있으면 그대로 씁니다."""
    canon = store.key("canonical.key")
    pub_hex = X.uncompressed_hex(canon.public_key())
    if store.has("registration.json"):
        return json.loads(store.read("registration.json")), canon
    body = json.dumps({"deviceType": device_type, "publicKey": pub_hex}).encode()
    st, resp, h = _http("POST", f"{ra_url}/dcms/device/na", body, ctype="application/json")
    if st == 400 and b"already exists" in resp:
        reg = {"publicKey": pub_hex, "deviceType": device_type, "status": "already registered"}
    else:
        _ok(st, resp, h, "장치 등록")
        reg = json.loads(resp)
    store.write("registration.json", json.dumps(reg, indent=2).encode())
    return reg, canon


# ------------------------------------------------------------ 1. 등록인증서
CERT_REQUEST_PERMISSIONS = [
    # 이 등록인증서로 응용인증서를 요청할 수 있는 범위 (1609.2.1 EeEcaCertRequest: certRequestPermissions PRESENT)
    {"subjectPermissions": ("all", 0), "minChainLength": 0, "chainLengthRange": 0,
     "eeType": (0b11000000, 8)},
]


def enroll(store, canon, eca_url=ECA_URL):
    """→ (등록인증서 COER, 등록 비밀키, ECA 사슬 [eca, ...])"""
    if store.has("enrollment.cert") and store.has("enrollment.key"):
        chain = [store.read(f"enrollment-chain-{i}.cert") for i in range(_count(store, "enrollment-chain-"))]
        return store.read("enrollment.cert"), store.key("enrollment.key"), chain

    k = X.new_key()                                   # 암묵적 인증서용 임시키 k
    now = time32()
    pub = canon.public_key().public_numbers()
    canonical_id = X.sha256(pub.x.to_bytes(32, "big") + pub.y.to_bytes(32, "big")).hex()
    req = {
        "version": 2, "generationTime": now, "type": "implicit",
        "tbsCert": {
            "id": ("none", 0), "cracaId": b"\x00\x00\x00", "crlSeries": 0,
            "validityPeriod": {"start": now, "duration": ("years", 6)},
            "certRequestPermissions": CERT_REQUEST_PERMISSIONS,
            "verifyKeyIndicator": ("verificationKey",
                                   ("ecdsaNistP256", X.point_to_asn(X.pubkey_to_point(k.public_key())))),
        },
        "canonicalId": canonical_id,
    }
    scoped = {"version": 2, "content": ("eca-ee", ("eeEcaCertRequest", req))}
    spdu = signed_cert_request(scoped, canon)          # 대표키로 자체 서명
    st, body, h = _http("POST", f"{eca_url}/v3/enrollment-certificate", spdu,
                        ctype="application/octet-stream")
    _ok(st, body, h, "등록인증서 요청")

    inner, signer = open_signed(body)
    pdu = dec(D21.ScmsPdu, inner)
    resp = pdu["content"][1][1]                       # ('eca-ee', ('ecaEeCertResponse', {...}))
    chain = [cert_coer(c) for c in resp["ecaCertChain"]]
    eca = chain[0]
    eca_pub = X.point_to_pubkey(_explicit_point(eca))
    open_signed(body, eca_pub)                         # ECA 서명 확인

    enr = cert_coer(resp["certificate"])
    ev = resp["certificate"]
    if ev["type"] != "implicit":
        raise ScmsError("등록인증서가 암묵적 형식이 아닙니다")
    tbs = tbs_coer(ev["toBeSigned"])
    r = int.from_bytes(resp["privateKeyInfo"], "big")
    d = X.implicit_private(tbs, eca, X.priv_int(k), r)
    Q = X.implicit_public(tbs, eca, X.point_from_asn(ev["toBeSigned"]["verifyKeyIndicator"][1]),
                          X.pubkey_to_point(eca_pub))
    if X.pubkey_to_point(X.key_from_int(d).public_key()) != Q:
        raise ScmsError("등록인증서 비밀키 복원 실패 (d·G ≠ Q)")

    store.write("enrollment.cert", enr)
    store.write("enrollment.key", d.to_bytes(32, "big"), secret=True)
    for i, c in enumerate(chain):
        store.write(f"enrollment-chain-{i}.cert", c)
    return enr, X.key_from_int(d), chain


def _count(store, prefix):
    return len([f for f in os.listdir(store.dir) if f.startswith(prefix)])


def _explicit_point(coer):
    tbs = dec(D2.Certificate, coer)["toBeSigned"]
    kind, v = tbs["verifyKeyIndicator"]
    if kind != "verificationKey":
        raise ScmsError("명시적 인증서가 아닙니다")
    return X.point_from_asn(v[1])


# ------------------------------------------------------------ 2~3. 응용인증서
def authorize(store, enr_cert, enr_key, psids, ra_url=RA_URL, hours=168, wait_s=60):
    """응용인증서(명시적, NonButterfly)를 요청하고 다운로드합니다.
    → (응용인증서 COER, 응용 비밀키)"""
    app_key = store.key("app.key")
    ra_cert = fetch_ra_cert(ra_url)

    if store.has("app-request.hash"):
        req_hash = store.read("app-request.hash").decode()
        next_dl = 0
    else:
        req_hash, next_dl = _request_app_cert(store, enr_cert, enr_key, app_key, psids, ra_cert, ra_url, hours)

    # 3. 다운로드: RA가 알려 준 다운로드 시각(nextDlTime)까지 기다렸다가 받는다
    filename = f"{req_hash.upper()}.zip"
    wait = next_dl + EPOCH_2004 - time.time()
    if 0 < wait < wait_s:
        time.sleep(wait)
    deadline = time.time() + wait_s
    while True:
        dl = {"version": 2, "content": ("ee-ra", ("eeRaDownloadRequest",
                                                  {"generationTime": time32(), "filename": filename}))}
        signed = make_signed(enc(D21.ScmsPdu, dl), enr_key, enr_cert)
        auth = base64.b64encode(encrypt_to(signed, ra_cert)).decode()
        st, body, h = _http("GET", f"{ra_url}/v3/authorization-certificate",
                            headers={"Ieee-1609.2.1-Authorization": auth})
        if st in (200, 202):
            break
        if st == 404 and time.time() < deadline:
            time.sleep(3)                              # 아직 ACA가 발급 중
            continue
        os.remove(store.path("app-request.hash"))      # 다음 실행 때 새로 요청하도록
        _ok(st, body, h, "응용인증서 다운로드")

    zf = zipfile.ZipFile(io.BytesIO(body))
    names = [n for n in zf.namelist() if not n.endswith("/")]
    if not names:
        raise ScmsError("다운로드한 zip이 비어 있습니다")
    resp = _aca_response(zf.read(names[0]))
    app_cert = cert_coer(resp["certificate"])
    if _explicit_point(app_cert) != X.pubkey_to_point(app_key.public_key()):
        raise ScmsError("받은 응용인증서의 공개키가 내 키와 다릅니다")
    store.write("app.cert", app_cert)
    os.remove(store.path("app-request.hash"))
    return app_cert, app_key


# ------------------------------------------------------------ 전체 순서
def provision(name, device_type, psids, ra_url=RA_URL, eca_url=ECA_URL, log=print):
    """장치 하나가 인증서를 갖추기까지 전체 과정.
    → dict(app_cert, app_key, enr_cert, chain=[aca, ica, root])"""
    store = Store(name)
    reg, canon = register(store, device_type, ra_url)
    log(f"[{name}] 등록 완료 ({device_type})")
    enr_cert, enr_key, _ = enroll(store, canon, eca_url)
    log(f"[{name}] 등록인증서 OK  id={hid8(enr_cert).hex()}")
    if store.has("app.cert") and store.has("app.key") and _app_valid(store.read("app.cert")):
        app_cert, app_key = store.read("app.cert"), store.key("app.key")
        log(f"[{name}] 응용인증서 재사용  id={hid8(app_cert).hex()}")
    else:
        if store.has("app.key") and not store.has("app-request.hash"):
            os.remove(store.path("app.key"))           # 새 응용인증서에는 새 키
        app_cert, app_key = authorize(store, enr_cert, enr_key, psids, ra_url)
        log(f"[{name}] 응용인증서 발급  id={hid8(app_cert).hex()}")
    chain = fetch_chain(app_cert, ra_url)
    return {"app_cert": app_cert, "app_key": app_key, "enr_cert": enr_cert, "chain": chain}


def _request_app_cert(store, enr_cert, enr_key, app_key, psids, ra_cert, ra_url, hours, tries=3):
    """2. 응용인증서 요청 → (requestHash hex, nextDlTime)"""
    for attempt in range(tries):
        now = time32()
        req = {
            "version": 2, "generationTime": now, "type": "explicit",
            "tbsCert": {
                "id": ("none", 0), "cracaId": b"\x00\x00\x00", "crlSeries": 0,
                "validityPeriod": {"start": now, "duration": ("hours", hours)},
                "appPermissions": [{"psid": p} for p in psids],
                "verifyKeyIndicator": ("verificationKey",
                                       ("ecdsaNistP256", X.point_to_asn(X.pubkey_to_point(app_key.public_key())))),
            },
        }
        scoped = {"version": 2, "content": ("ee-ra", ("eeRaCertRequest", req))}
        signed = signed_cert_request(scoped, enr_key, enr_cert)    # 등록인증서로 서명
        spdu = encrypt_to(signed, ra_cert)                         # RA만 열 수 있게 암호화
        st, body, h = _http("POST", f"{ra_url}/v3/authorization-certificate", spdu,
                            ctype="application/octet-stream")
        err = h.get("Ieee-1609.2.1-Error", "")
        if st == 400 and err in ("400-50", "400-77") and attempt + 1 < tries:
            time.sleep(1)                              # 시각 경계에 걸림: 새 generationTime으로 다시
            continue
        _ok(st, body, h, "응용인증서 요청")
        inner, _ = open_signed(body, X.point_to_pubkey(_explicit_point(ra_cert)))   # RA 서명 확인
        ack = dec(D21.ScmsPdu, inner)["content"][1][1]
        req_hash = ack["requestHash"].hex()
        store.write("app-request.hash", req_hash.encode())
        return req_hash, ack["nextDlTime"]
    raise ScmsError("응용인증서 요청 실패")


def _aca_response(raw):
    """zip 안 파일 → AcaEeCertResponse 값.
    OpenSCMS는 AcaResponse(plain) 형태로 저장하고, 표준 그대로면 AcaEeCertResponsePlainSpdu입니다. 둘 다 받습니다."""
    try:
        kind, spdu = dec(G.Ieee1609Dot2Dot1AcaRaInterface.AcaResponse, raw)
        v = spdu if isinstance(spdu, dict) else dec(D2.Ieee1609Dot2Data, spdu)
    except Exception:
        kind, v = "plain", dec(D2.Ieee1609Dot2Data, raw)
    if kind != "plain" or v["content"][0] != "unsecuredData":
        raise ScmsError(f"지원하지 않는 응답 형식: {kind}/{v['content'][0]} (NonButterfly 평문만 지원)")
    return dec(D21.ScmsPdu, v["content"][1])["content"][1][1]


def _app_valid(coer, margin_s=600):
    vp = dec(D2.Certificate, coer)["toBeSigned"]["validityPeriod"]
    start = vp["start"] + EPOCH_2004
    unit, n = vp["duration"]
    sec = {"microseconds": 1e-6, "milliseconds": 1e-3, "seconds": 1, "minutes": 60,
           "hours": 3600, "sixtyHours": 216000, "years": 31556952}[unit] * n
    return start <= time.time() + 5 and time.time() + margin_s < start + sec
