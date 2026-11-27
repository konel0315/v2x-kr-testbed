"""위치 계산 도우미: 위경도 두 점 사이를 '내 진행 방향 기준 앞뒤·좌우 거리(m)'로 바꾼다.
교차로 하나(수백 m) 범위라서 평면 근사로 충분하다."""
import math

M_PER_DEG_LAT = 111_320.0


def offset_m(lat0, lon0, lat, lon):
    """(lat0, lon0)에서 (lat, lon)까지 동(x)·북(y) 미터"""
    x = (lon - lon0) * M_PER_DEG_LAT * math.cos(math.radians(lat0))
    y = (lat - lat0) * M_PER_DEG_LAT
    return x, y


def relative(lat0, lon0, heading_deg, lat, lon):
    """내 위치·방향(북 0도, 시계 방향) 기준으로 상대 위치 (앞 거리, 오른쪽 거리). 뒤·왼쪽은 음수."""
    x, y = offset_m(lat0, lon0, lat, lon)
    h = math.radians(heading_deg)
    ahead = x * math.sin(h) + y * math.cos(h)
    right = x * math.cos(h) - y * math.sin(h)
    return ahead, right


def velocity(speed, heading_deg):
    """속도(m/s)와 방향 -> 동(x)·북(y) 속도 성분"""
    h = math.radians(heading_deg)
    return speed * math.sin(h), speed * math.cos(h)


def distance_m(lat0, lon0, lat, lon):
    x, y = offset_m(lat0, lon0, lat, lon)
    return math.hypot(x, y)


def bearing_deg(lat0, lon0, lat, lon):
    """(lat0, lon0)에서 본 (lat, lon)의 방위각 (북 0도, 시계 방향)"""
    x, y = offset_m(lat0, lon0, lat, lon)
    return math.degrees(math.atan2(x, y)) % 360


def angle_diff(a, b):
    """두 방향의 차이 (0~180도)"""
    return abs((a - b + 180) % 360 - 180)
