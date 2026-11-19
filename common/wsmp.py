"""IEEE 1609.3 WSMP 헤더 (짧은 형태: 옵션 없음, TPID 0).

  [N-헤더 1B] subtype 0 | option 0 | version 3  -> 0x03
  [T-헤더]    TPID 1B(0) + PSID(p-encoded 1~4B, IEEE 1609.12) + 길이(1~2B)
  [데이터]
"""
WSMP_VERSION = 3


def _psid_encode(psid):
    """PSID를 p-encoded 바이트로. 이 프로젝트의 PSID 값(0x20, 0x8002, 0xE0000017)은
    V2X-Hub·RSU 4.1과 같이 이미 p-encoded 표기이므로 바이트 그대로 쓴다.
    첫 바이트 앞 비트: 0xxx=1B, 10xx=2B, 110x=3B, 1110=4B."""
    for n in (1, 2, 3, 4):
        if psid < (1 << (8 * n)):
            b = psid.to_bytes(n, "big")
            if _psid_len(b[0]) != n:
                raise ValueError(f"p-encoded PSID 아님: {psid:#x}")
            return b
    raise ValueError(f"PSID 범위 초과: {psid:#x}")


def _psid_len(b0):
    return 1 if b0 < 0x80 else 2 if b0 < 0xC0 else 3 if b0 < 0xE0 else 4


def _psid_decode(buf):
    n = _psid_len(buf[0])
    return int.from_bytes(buf[:n], "big"), n


def _len_encode(n):
    return bytes([n]) if n < 0x80 else (0x8000 | n).to_bytes(2, "big")


def _len_decode(buf):
    if buf[0] < 0x80:
        return buf[0], 1
    return int.from_bytes(buf[:2], "big") & 0x3FFF, 2


def encode(psid, data):
    return bytes([WSMP_VERSION, 0]) + _psid_encode(psid) + _len_encode(len(data)) + data


def decode(wsm):
    """WSM 바이트 -> (psid, data). 형식이 틀리면 ValueError."""
    if len(wsm) < 4 or (wsm[0] & 0x07) != WSMP_VERSION or wsm[1] != 0:
        raise ValueError("WSMP 헤더 아님")
    psid, n1 = _psid_decode(wsm[2:])
    length, n2 = _len_decode(wsm[2 + n1:])
    start = 2 + n1 + n2
    data = wsm[start:start + length]
    if len(data) != length:
        raise ValueError("WSMP 길이 불일치")
    return psid, data
