"""IEEE 1609.2 보안: 명시적 인증서, 서명(SignedData), 검증.

ASN.1 구조는 IEEE 1609.2 공개 ASN.1(pycrate 내장 ITS_IEEE1609_2)을 쓰고, 인코딩은 COER이다.
암호는 ECDSA NIST P-256 + SHA-256 (Python cryptography).

서명 입력 (IEEE 1609.2 5.3.1):  SHA256( SHA256(서명 대상 COER) || SHA256(서명자 인증서 COER) )
  - 자체 서명(루트) 인증서는 서명자 인증서 자리에 빈 문자열을 쓴다.
HashedId8 = SHA256(인증서 COER)의 마지막 8바이트

검증 순서 (계획서 6단계): 1 서명  2 권한(PSID)  3 유효기간  4 발급 체인
"""
import hashlib
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import (Prehashed, decode_dss_signature,
                                                             encode_dss_signature)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from pycrate_asn1dir import ITS_IEEE1609_2 as _M

_CERT = _M.Ieee1609Dot2.Certificate
_TBS_CERT = _M.Ieee1609Dot2.ToBeSignedCertificate
_DATA = _M.Ieee1609Dot2.Ieee1609Dot2Data
_TBS_DATA = _M.Ieee1609Dot2.ToBeSignedData

EPOCH_2004 = 1072915200          # 2004-01-01 00:00:00 UTC (1609.2 시각의 기준점)


# ---------------------------------------------------------------- 시각
def time32(t=None):
    """1609.2 Time32: 2004년부터 지난 초"""
    return int((time.time() if t is None else t) - EPOCH_2004)


def time64(t=None):
    """1609.2 Time64: 2004년부터 지난 마이크로초"""
    return int(((time.time() if t is None else t) - EPOCH_2004) * 1_000_000)


def _duration_seconds(d):
    kind, n = d
    return n * {"microseconds": 1e-6, "milliseconds": 1e-3, "seconds": 1, "minutes": 60,
                "hours": 3600, "sixtyHours": 216000, "years": 31556952}[kind]


# ---------------------------------------------------------------- 키·해시
def new_key():
    return ec.generate_private_key(ec.SECP256R1())


def _sha256(b):
    return hashlib.sha256(b).digest()


def _point(pub):
    """공개키 -> EccP256CurvePoint (압축형)"""
    raw = pub.public_bytes(Encoding.X962, PublicFormat.CompressedPoint)
    return ("compressed-y-0" if raw[0] == 2 else "compressed-y-1", raw[1:])


def _pubkey(point):
    kind, val = point
    if kind == "compressed-y-0":
        raw = b"\x02" + val
    elif kind == "compressed-y-1":
        raw = b"\x03" + val
    elif kind == "uncompressedP256":
        raw = b"\x04" + val["x"] + val["y"]
    else:
        raise ValueError("지원하지 않는 공개키 형식")
    return ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), raw)


def _sign(key, tbs, signer_cert_bytes):
    digest = _sha256(_sha256(tbs) + _sha256(signer_cert_bytes))
    r, s = decode_dss_signature(key.sign(digest, ec.ECDSA(Prehashed(hashes.SHA256()))))
    return ("ecdsaNistP256Signature", {"rSig": ("x-only", r.to_bytes(32, "big")),
                                       "sSig": s.to_bytes(32, "big")})


def _verify(pub, sig, tbs, signer_cert_bytes):
    kind, val = sig
    if kind != "ecdsaNistP256Signature":
        return False
    r = int.from_bytes(val["rSig"][1] if isinstance(val["rSig"][1], bytes) else val["rSig"][1]["x"], "big")
    s = int.from_bytes(val["sSig"], "big")
    digest = _sha256(_sha256(tbs) + _sha256(signer_cert_bytes))
    try:
        pub.verify(encode_dss_signature(r, s), digest, ec.ECDSA(Prehashed(hashes.SHA256())))
        return True
    except InvalidSignature:
        return False


# ---------------------------------------------------------------- 인증서
class Cert:
    """COER 바이트로 된 명시적 인증서 하나."""

    def __init__(self, coer):
        self.coer = bytes(coer)
        _CERT.from_coer(self.coer)
        self.val = _CERT.get_val()
        tbs = self.val["toBeSigned"]
        self.name = tbs["id"][1] if tbs["id"][0] == "name" else tbs["id"][0]
        self.start = tbs["validityPeriod"]["start"] + EPOCH_2004
        self.end = self.start + _duration_seconds(tbs["validityPeriod"]["duration"])
        self.psids = [p["psid"] for p in tbs.get("appPermissions", [])]
        self.is_ca = "certIssuePermissions" in tbs
        self.pub = _pubkey(tbs["verifyKeyIndicator"][1][1])
        self.issuer = self.val["issuer"]                  # ("self", "sha256") 또는 ("sha256AndDigest", id8)
        _TBS_CERT.set_val(tbs)
        self.tbs_coer = _TBS_CERT.to_coer()

    @property
    def hashed_id8(self):
        return _sha256(self.coer)[-8:]

    def signed_by(self, issuer):
        """issuer(인증서 객체, 자체 서명이면 None)의 키로 서명이 맞는지"""
        key = self.pub if issuer is None else issuer.pub
        return _verify(key, self.val["signature"], self.tbs_coer,
                       b"" if issuer is None else issuer.coer)

    def __repr__(self):
        return f"Cert({self.name}, psid={[hex(p) for p in self.psids]}, ca={self.is_ca})"


def issue_cert(name, subject_pub, issuer_key, issuer_cert=None, psids=None, ca=False,
               start=None, duration_s=7 * 24 * 3600):
    """명시적 인증서를 만든다. issuer_cert가 None이면 자체 서명(루트)."""
    start = time32(start)
    duration = ("seconds", duration_s) if duration_s <= 65535 else ("hours", min(duration_s // 3600, 65535))
    tbs = {
        "id": ("name", name),
        "cracaId": b"\x00\x00\x00",
        "crlSeries": 0,
        "validityPeriod": {"start": start, "duration": duration},
        "verifyKeyIndicator": ("verificationKey", ("ecdsaNistP256", _point(subject_pub))),
    }
    if psids:
        tbs["appPermissions"] = [{"psid": p} for p in psids]
    if ca:
        # 하위 인증서 발급 권한: 모든 PSID, 체인 길이 1 이상, 대상은 종단(app)과 CA 모두
        tbs["certIssuePermissions"] = [{"subjectPermissions": ("all", 0), "minChainLength": 1,
                                        "chainLengthRange": 0, "eeType": (0b11, 8)}]
    _TBS_CERT.set_val(tbs)
    tbs_coer = _TBS_CERT.to_coer()
    signer_bytes = b"" if issuer_cert is None else issuer_cert.coer
    cert = {
        "version": 3,
        "type": "explicit",
        "issuer": ("self", "sha256") if issuer_cert is None
        else ("sha256AndDigest", issuer_cert.hashed_id8),
        "toBeSigned": tbs,
        "signature": _sign(issuer_key, tbs_coer, signer_bytes),
    }
    _CERT.set_val(cert)
    return Cert(_CERT.to_coer())


# ---------------------------------------------------------------- 서명된 데이터 (SPDU)
def sign_data(payload, psid, key, cert, gen_time=None):
    """payload(J2735 MessageFrame 바이트)를 1609.2 SignedData로 감싼다. 서명자 인증서를 통째로 넣는다."""
    tbs = {
        "payload": {"data": {"protocolVersion": 3, "content": ("unsecuredData", payload)}},
        "headerInfo": {"psid": psid, "generationTime": time64(gen_time)},
    }
    _TBS_DATA.set_val(tbs)
    tbs_coer = _TBS_DATA.to_coer()
    data = {"protocolVersion": 3, "content": ("signedData", {
        "hashId": "sha256",
        "tbsData": tbs,
        "signer": ("certificate", [cert.val]),
        "signature": _sign(key, tbs_coer, cert.coer),
    })}
    _DATA.set_val(data)
    return _DATA.to_coer()


def is_spdu(buf):
    """1609.2 데이터(첫 바이트 = 프로토콜 버전 3)인지. J2735 MessageFrame은 0x00으로 시작한다."""
    return len(buf) > 2 and buf[0] == 3


def unwrap_unverified(spdu):
    """검증 없이 내용만 꺼낸다 (검증 끔 시험용)."""
    _DATA.from_coer(spdu)
    v = _DATA.get_val()
    if v["content"][0] == "unsecuredData":
        return v["content"][1]
    return v["content"][1]["tbsData"]["payload"]["data"]["content"][1]


# ---------------------------------------------------------------- 검증
class VerifyError(Exception):
    def __init__(self, step, reason):
        super().__init__(reason)
        self.step = step        # 1 서명, 2 권한, 3 유효기간, 4 발급 체인
        self.reason = reason


class Verifier:
    """신뢰하는 루트 인증서와 CA 체인(중간 CA)으로 SPDU를 검증한다."""

    def __init__(self, root, intermediates=(), clock_skew=5.0):
        if not root.signed_by(None):
            raise ValueError("루트 인증서 자체 서명이 틀림")
        self.root = root
        self.ca = {root.hashed_id8: root}
        self.skew = clock_skew
        for c in intermediates:
            self.ca[c.hashed_id8] = c

    def _chain_ok(self, cert, now):
        """cert에서 루트까지 거슬러 올라가며 서명과 기간을 확인"""
        cur, depth = cert, 0
        while depth < 5:
            kind, val = cur.issuer
            if kind == "self":
                return cur.hashed_id8 == self.root.hashed_id8 and cur.signed_by(None)
            issuer = self.ca.get(val)
            if issuer is None or not issuer.is_ca:
                return False
            if not cur.signed_by(issuer) or not (issuer.start <= now <= issuer.end):
                return False
            cur, depth = issuer, depth + 1
        return False

    def verify(self, spdu, expected_psid, now=None):
        """검증을 통과하면 (payload, 서명자 인증서) 반환. 실패하면 VerifyError."""
        now = time.time() if now is None else now
        try:
            _DATA.from_coer(spdu)
            data = _DATA.get_val()
        except Exception:
            raise VerifyError(1, "DECODE_FAIL")
        if data["content"][0] != "signedData":
            raise VerifyError(1, "UNSIGNED")
        sd = data["content"][1]
        if sd["signer"][0] != "certificate":
            raise VerifyError(1, "NO_SIGNER_CERT")
        _CERT.set_val(sd["signer"][1][0])
        cert = Cert(_CERT.to_coer())
        _TBS_DATA.set_val(sd["tbsData"])
        tbs_coer = _TBS_DATA.to_coer()
        # 1 서명
        if not _verify(cert.pub, sd["signature"], tbs_coer, cert.coer):
            raise VerifyError(1, "BAD_SIGNATURE")
        # 2 권한: 메시지의 PSID가 인증서 권한에 있고, 받은 채널(WSMP)의 PSID와 같은가
        psid = sd["tbsData"]["headerInfo"]["psid"]
        if psid != expected_psid or psid not in cert.psids:
            raise VerifyError(2, "NO_PERMISSION")
        # 3 유효기간: 생성 시각과 현재 시각이 모두 인증서 기간 안인가
        gen = sd["tbsData"]["headerInfo"].get("generationTime", 0) / 1e6 + EPOCH_2004
        if not (cert.start - self.skew <= gen <= cert.end) or not (cert.start - self.skew <= now <= cert.end):
            raise VerifyError(3, "CERT_EXPIRED")
        # 4 발급 체인: 신뢰하는 루트까지 이어지는가
        if not self._chain_ok(cert, now):
            raise VerifyError(4, "UNKNOWN_ISSUER")
        return sd["tbsData"]["payload"]["data"]["content"][1], cert
