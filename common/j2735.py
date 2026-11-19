"""J2735 메시지 인코딩·디코딩 (SAE J2735 2024, UPER).

SAE에서 받은 ASN.1 파일을 pycrate로 컴파일한 모듈(common/j2735_gen.py)을 사용한다.
그 모듈은 scripts/build_j2735.sh 로 만들며, SAE 라이선스 때문에 GitHub에 올리지 않는다.
"""
import time

from common import j2735_gen  # scripts/build_j2735.sh 가 만든 파일

_MF = j2735_gen.MessageFrame.MessageFrame

BSM_ID = 20   # J2735 DSRCmsgID: basicSafetyMessage
MAP_ID = 18   # mapData
SPAT_ID = 19  # signalPhaseAndTimingMessage


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def sec_mark_now():
    """현재 분 안에서 몇 밀리초가 지났는지 (DSecond, 0..59999)."""
    return int(time.time() * 1000) % 60000


def make_bsm(msg_cnt, temp_id, lat, lon, speed, heading, accel=0.0,
             width_cm=180, length_cm=450):
    """차량 상태로 J2735 BSM(MessageFrame)을 만들어 UPER 바이트로 돌려준다.

    lat, lon: 도 / speed: m/s / heading: 도(북 0, 시계 방향) / accel: m/s^2
    temp_id: 4바이트 임시 ID
    """
    core = {
        "msgCnt": msg_cnt,                                   # 0..127 순환
        "id": temp_id,                                       # 4바이트
        "secMark": sec_mark_now(),                           # ms
        "lat": int(round(lat * 1e7)),                        # 1/10 마이크로도
        "long": int(round(lon * 1e7)),
        "elev": -4096,                                       # 높이 모름
        "accuracy": {"semiMajor": 255, "semiMinor": 255,     # 정확도 모름
                     "orientation": 65535},
        "transmission": "forwardGears",
        "speed": _clamp(int(round(speed / 0.02)), 0, 8190),  # 0.02 m/s 단위
        "heading": int(round((heading % 360) / 0.0125)) % 28800,  # 0.0125도 단위
        "angle": 127,                                        # 조향각 모름
        "accelSet": {"long": _clamp(int(round(accel * 100)), -2000, 2000),
                     "lat": 2001, "vert": -127, "yaw": 0},   # 2001/-127 = 모름
        "brakes": {"wheelBrakes": (0b10000, 5),              # unavailable 비트
                   "traction": "unavailable", "abs": "unavailable",
                   "scs": "unavailable", "brakeBoost": "unavailable",
                   "auxBrakes": "unavailable"},
        "size": {"width": width_cm, "length": length_cm},
    }
    _MF.set_val({"messageId": BSM_ID,
                 "value": ("BasicSafetyMessage", {"coreData": core})})
    return _MF.to_uper()


def decode(frame):
    """UPER 바이트를 MessageFrame으로 풀어 (메시지 이름, 내용 dict)로 돌려준다."""
    _MF.from_uper(frame)
    v = _MF.get_val()
    return v["value"][0], v["value"][1]
