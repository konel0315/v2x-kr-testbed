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
TIM_ID = 31   # travelerInformation (KS R 1600-5)
PSM_ID = 32   # personalSafetyMessage (KS R 1600-6)

ITIS_ROAD_CONSTRUCTION = 1025   # ITIS 코드(SAE J2540): 도로 공사


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


def encode_frame(msg_id, name, value):
    """임의의 J2735 메시지를 MessageFrame UPER로 인코딩한다."""
    _MF.set_val({"messageId": msg_id, "value": (name, value)})
    return _MF.to_uper()


def moy_and_dsecond(t=None):
    """(올해 몇 번째 분인지, 그 분 안의 ms) — SPaT·MAP 시각 필드용."""
    t = time.time() if t is None else t
    tm = time.gmtime(t)
    moy = (tm.tm_yday - 1) * 1440 + tm.tm_hour * 60 + tm.tm_min
    return moy, int(t * 1000) % 60000


def time_mark(offset_s, t=None):
    """지금부터 offset_s초 뒤를 J2735 TimeMark(현재 시각의 '분·초'를 0.1초 단위, 0..35999)로."""
    t = (time.time() if t is None else t) + offset_s
    return int(t * 10) % 36000


def make_spat(intersection_id, states, revision=1, name=None):
    """SPaT를 만든다 (시험용·공격 시나리오용. 정상 SPaT는 V2X-Hub가 만든다).

    states: {signalGroup: (eventState 이름, 남은 초)}
      eventState 예: "stop-And-Remain"(빨강), "protected-clearance"(노랑),
                    "protected-Movement-Allowed"(초록)
    """
    moy, ds = moy_and_dsecond()
    movements = [{"signalGroup": sg,
                  "state-time-speed": [{"eventState": st,
                                        "timing": {"minEndTime": time_mark(remain)}}]}
                 for sg, (st, remain) in sorted(states.items())]
    inter = {"id": {"id": intersection_id}, "revision": revision,
             "status": (0, 16), "moy": moy, "timeStamp": ds, "states": movements}
    if name:
        inter["name"] = name
    return encode_frame(SPAT_ID, "SPAT", {"intersections": [inter]})


def make_psm(msg_cnt, temp_id, lat, lon, speed, heading, kind="aPEDESTRIAN"):
    """보행자 단말의 위치로 J2735 PSM(개인 안전 메시지, KS R 1600-6)을 만든다.

    kind: aPEDESTRIAN(보행자), aPEDALCYCLIST(자전거), aPUBLICSAFETYWORKER(도로 작업자)
    """
    psm = {
        "basicType": kind,
        "secMark": sec_mark_now(),
        "msgCnt": msg_cnt,
        "id": temp_id,                                       # 4바이트 임시 ID
        "position": {"lat": int(round(lat * 1e7)), "long": int(round(lon * 1e7))},
        "accuracy": {"semiMajor": 255, "semiMinor": 255, "orientation": 65535},
        "speed": _clamp(int(round(speed / 0.02)), 0, 8190),
        "heading": int(round((heading % 360) / 0.0125)) % 28800,
    }
    return encode_frame(PSM_ID, "PersonalSafetyMessage", psm)


def psm_state(psm):
    """PSM 내용 -> 위도, 경도, 속도(m/s), 방향(도)"""
    return {"lat": psm["position"]["lat"] / 1e7, "lon": psm["position"]["long"] / 1e7,
            "speed": psm["speed"] * 0.02, "heading": psm["heading"] * 0.0125,
            "kind": psm["basicType"], "id": psm["id"]}


def minute_of_year(t=None):
    tm = time.gmtime(time.time() if t is None else t)
    return tm.tm_year, (tm.tm_yday - 1) * 1440 + tm.tm_hour * 60 + tm.tm_min


def make_tim(msg_cnt, packet_id, lat, lon, radius_m, speed_kmh, duration_min=60, start=None):
    """공사 구간 안내 TIM(여행자 정보 메시지, KS R 1600-5)을 만든다.

    구간: 중심(lat, lon), 반지름 radius_m 인 원
    내용: 도로 공사(ITIS 1025) + 권고 속도 글자("30 km/h")
    """
    year, moy = minute_of_year(start)
    anchor = {"lat": int(round(lat * 1e7)), "long": int(round(lon * 1e7))}
    frame = {
        "doNotUse1": 0, "frameType": "advisory",
        "msgId": ("roadSignID", {"position": anchor, "viewAngle": (0xFFFF, 16),   # 모든 방향
                                 "mutcdCode": "warning"}),
        "startYear": year, "startTime": moy, "durationTime": duration_min,
        "priority": 5, "doNotUse2": 0,
        "regions": [{"name": "work zone", "anchor": anchor,
                     "description": ("geometry", {
                         "direction": (0xFFFF, 16), "extent": "useInstantlyOnly",
                         "circle": {"center": anchor, "radius": int(radius_m), "units": "meter"}})}],
        "doNotUse3": 0, "doNotUse4": 0,
        "content": ("workZone", [{"item": ("itis", ITIS_ROAD_CONSTRUCTION)},
                                 {"item": ("text", f"{int(speed_kmh)} km/h")}]),
    }
    tim = {"msgCnt": msg_cnt, "packetID": packet_id, "dataFrames": [frame]}
    return encode_frame(TIM_ID, "TravelerInformation", tim)


def tim_zones(tim, now=None):
    """TIM 내용 -> 지금 유효한 공사 구간 목록 [{lat, lon, radius, speed(m/s), text}]"""
    import re
    year, moy = minute_of_year(now)
    out = []
    for f in tim.get("dataFrames", []):
        start = f["startTime"]
        if f.get("startYear", year) == year and not (start <= moy < start + f["durationTime"]):
            continue
        kind, items = f["content"]
        texts = [v for k, v in (i["item"] for i in items) if k == "text"]
        itis = [v for k, v in (i["item"] for i in items) if k == "itis"]
        m = re.search(r"(\d+)\s*km/h", " ".join(texts))
        for r in f.get("regions", []):
            dk, d = r.get("description", (None, None))
            if dk != "geometry" or d["circle"]["units"] != "meter":
                continue
            c = d["circle"]["center"]
            out.append({"lat": c["lat"] / 1e7, "lon": c["long"] / 1e7, "radius": d["circle"]["radius"],
                        "speed": int(m.group(1)) / 3.6 if m else None, "kind": kind,
                        "construction": ITIS_ROAD_CONSTRUCTION in itis, "text": " ".join(texts)})
    return out
