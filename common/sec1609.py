"""IEEE 1609.2 보안: 인증서, 서명(SignedData), 검증.

ASN.1 구조는 IEEE 1609.2-2022 / 1609.2.1-2022 공개 ASN.1(OpenSCMS가 쓰는 것과 같은 판)을
pycrate로 변환한 common/ieee1609_gen.py를 쓰고, 인코딩은 COER이다. (scripts/build_ieee1609.sh로 만든다)
암호는 ECDSA NIST P-256 + SHA-256.

서명 입력 (IEEE 1609.2 5.3.1):  SHA256( SHA256(서명 대상 COER) || SHA256(서명자 인증서 COER) )
  - 자체 서명(루트) 인증서는 서명자 인증서 자리에 빈 문자열을 쓴다.
HashedId8 = SHA256(인증서 COER)의 마지막 8바이트

인증서는 OpenSCMS(SCMS)가 발급한다. CA 인증서의 역할(root, ica, aca ...)은
PSID 35(SecurityMgmt)의 SSP로 표시되고(1609.2.1), 응용인증서의 PSID 권한은 appPermissions에 있다.

검증 순서 (계획서 6단계): 1 서명  2 권한(PSID)  3 유효기간  4 발급 체인
"""
import time

from common import ieee1609_gen as _G
from common import scms_crypto as X

_CERT = _G.Ieee1609Dot2.Certificate
_TBS_CERT = _G.Ieee1609Dot2.ToBeSignedCertificate
_DATA = _G.Ieee1609Dot2.Ieee1609Dot2Data
_TBS_DATA = _G.Ieee1609Dot2.ToBeSignedData
_SSP = _G.Ieee1609Dot2Dot1Protocol.SecurityMgmtSsp

EPOCH_2004 = 1072915200          # 2004-01-01 00:00:00 UTC (1609.2 시각의 기준점)
PSID_SECURITY_MGMT = 35
CA_ROLES = {"root", "ica", "eca", "aca"}

_UNIT_S = {"microseconds": 1e-6, "milliseconds": 1e-3, "seconds": 1, "minutes": 60,
           "hours": 3600, "sixtyHours": 216000, "years": 31556952}


# ---------------------------------------------------------------- 시각
def time32(t=None):
    """Time32: 2004년부터 지난 초"""
    return int((time.time() if t is None else t) - EPOCH_2004)


def time64(t=None):
    """Time64: 2004년부터 지난 마이크로초"""
    return int(((time.time() if t is None else t) - EPOCH_2004) * 1_000_000)


def new_key():
    return X.new_key()


# ---------------------------------------------------------------- 인증서
class Cert:
    """COER 바이트로 된 1609.2 인증서 하나 (명시적/암묵적)."""

    def __init__(self, coer):
        self.coer = bytes(coer)
        _CERT.from_coer(self.coer)
        self.val = _CERT.get_val()
        tbs = self.val["toBeSigned"]
        self.type = self.val["type"]                       # explicit / implicit
        self.issuer = self.val["issuer"]                   # ("self", ...) 또는 ("sha256AndDigest", id8)
        self.start = tbs["validityPeriod"]["start"] + EPOCH_2004
        unit, n = tbs["validityPeriod"]["duration"]
        self.end = self.start + _UNIT_S[unit] * n
        perms = tbs.get("appPermissions", [])
        self.psids = [p["psid"] for p in perms]
        self.role = _role(perms)                           # root/ica/aca/... 또는 None(단말)
        self.is_ca = "certIssuePermissions" in tbs or self.role in CA_ROLES
        _TBS_CERT.set_val(tbs)
        self.tbs_coer = _TBS_CERT.to_coer()
        kind, v = tbs["verifyKeyIndicator"]
        self._point = X.point_from_asn(v[1] if kind == "verificationKey" else v)
        self.pub = X.point_to_pubkey(self._point) if kind == "verificationKey" else None
        self.hashed_id8 = X.sha256(self.coer)[-8:]
        cid = tbs["id"]
        self.name = cid[1] if cid[0] == "name" else self.hashed_id8.hex()   # 응용인증서는 익명(번호로 표시)

    def signed_by(self, issuer):
        """명시적 인증서: issuer(Cert, 자체 서명이면 None)의 키로 서명이 맞는지"""
        if self.type != "explicit":
            return False
        key = self.pub if issuer is None else issuer.pub
        if key is None:
            return False
        return X.verify(key, self.val["signature"], self.tbs_coer,
                        None if issuer is None else issuer.coer)

    def reconstruct(self, issuer):
        """암묵적 인증서: 발급자 공개키로 내 공개키를 복원 (1609.2 5.3.2)"""
        if self.type == "implicit" and self.pub is None and issuer.pub is not None:
            self.pub = X.point_to_pubkey(
                X.implicit_public(self.tbs_coer, issuer.coer, self._point, X.pubkey_to_point(issuer.pub)))
        return self.pub

    def __repr__(self):
        return f"Cert({self.name}, {self.role or 'ee'}, psid={[hex(p) for p in self.psids]})"


def _role(perms):
    for p in perms:
        if p["psid"] == PSID_SECURITY_MGMT and p.get("ssp", (None,))[0] == "opaque":
            try:
                _SSP.from_coer(p["ssp"][1])
                return _SSP.get_val()[0]
            except Exception:
                return None
    return None


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
        "signature": X.sign(key, tbs_coer, cert.coer),
    })}
    _DATA.set_val(data)
    return _DATA.to_coer()


def is_spdu(buf):
    """1609.2 데이터(첫 바이트 = 프로토콜 버전 3)인지. J2735 MessageFrame은 0x00으로 시작한다."""
    return len(buf) > 2 and buf[0] == 3


# ---------------------------------------------------------------- 검증
class VerifyError(Exception):
    def __init__(self, step, reason):
        super().__init__(reason)
        self.step = step        # 1 서명, 2 권한, 3 유효기간, 4 발급 체인
        self.reason = reason


class Verifier:
    """신뢰하는 루트 인증서와 중간 CA(ICA, ACA)로 SPDU를 검증한다."""

    def __init__(self, root, intermediates=(), clock_skew=5.0):
        if root.issuer[0] != "self" or not root.signed_by(None):
            raise ValueError("루트 인증서 자체 서명이 틀림")
        self.root = root
        self.ca = {root.hashed_id8: root}
        self.skew = clock_skew
        for c in intermediates:
            self.ca[c.hashed_id8] = c

    def _chain_ok(self, cert, now):
        """cert에서 루트까지 거슬러 올라가며 발급자 역할, 서명, 기간을 확인"""
        cur, depth = cert, 0
        while depth < 5:
            kind, val = cur.issuer
            if kind == "self":
                return cur.hashed_id8 == self.root.hashed_id8 and cur.signed_by(None)
            issuer = self.ca.get(val)
            if issuer is None or not issuer.is_ca:
                return False
            if cur is cert and issuer.role not in (None, "aca"):
                return False                       # 응용인증서는 ACA만 발급할 수 있다
            if not (issuer.start - self.skew <= now <= issuer.end):
                return False
            if cur.type == "implicit":
                if cur.reconstruct(issuer) is None:
                    return False
            elif not cur.signed_by(issuer):
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
        try:
            _CERT.set_val(sd["signer"][1][0])
            cert = Cert(_CERT.to_coer())
        except Exception:
            raise VerifyError(1, "BAD_CERT")
        if cert.type != "explicit":
            # 암묵적 인증서는 발급자를 알아야 공개키가 나오므로 체인 확인을 먼저 한다
            if not self._chain_ok(cert, now):
                raise VerifyError(4, "UNKNOWN_ISSUER")
        _TBS_DATA.set_val(sd["tbsData"])
        tbs_coer = _TBS_DATA.to_coer()
        # 1 서명
        if cert.pub is None or not X.verify(cert.pub, sd["signature"], tbs_coer, cert.coer):
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
