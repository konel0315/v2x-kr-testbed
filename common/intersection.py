"""MAP·SPaT 해석: OBU가 '내가 어느 차로에 있고, 정지선까지 몇 m이며, 내 신호가 무엇인지' 알아내는 부분."""
import math

M_PER_DEG_LAT = 111_320.0

RED = ("stop-And-Remain", "stop-Then-Proceed", "dark", "unavailable")
YELLOW = ("protected-clearance", "permissive-clearance", "caution-Conflicting-Traffic")
GREEN = ("protected-Movement-Allowed", "permissive-Movement-Allowed", "pre-Movement")


def color(event_state):
    if event_state in GREEN:
        return "GREEN"
    if event_state in YELLOW:
        return "YELLOW"
    return "RED"


_NODE_SIZE = {"node-XY1": 1, "node-XY2": 2, "node-XY3": 3,
              "node-XY4": 4, "node-XY5": 5, "node-XY6": 6}


class IntersectionMap:
    """해석된 MAP(교차로 1개). 진입 차로마다 정지선 위치·진행 방향·신호 그룹을 가진다."""

    def __init__(self, map_data):
        geo = map_data["intersections"][0]
        self.id = geo["id"]["id"]
        self.ref_lat = geo["refPoint"]["lat"] / 1e7
        self.ref_lon = geo["refPoint"]["long"] / 1e7
        self.lanes = []
        for lane in geo["laneSet"]:
            use = lane["laneAttributes"]["directionalUse"]  # (값, 비트 수)
            if not (use[0] >> (use[1] - 1)) & 1:             # ingressPath 비트
                continue
            pts, x, y = [], 0.0, 0.0
            for node in lane["nodeList"][1]:                 # ("nodes", [...])
                kind, off = node["delta"]
                if kind not in _NODE_SIZE:
                    continue
                x += off["x"] / 100.0                        # cm -> m
                y += off["y"] / 100.0
                pts.append((x, y))
            sgs = [c["signalGroup"] for c in lane.get("connectsTo", []) if "signalGroup" in c]
            if len(pts) < 2 or not sgs:
                continue
            # 노드 0 = 정지선, 노드 1 = 차로 바깥쪽. 진행 방향은 1 -> 0
            (x0, y0), (x1, y1) = pts[0], pts[1]
            heading = math.degrees(math.atan2(x0 - x1, y0 - y1)) % 360  # 북 0, 시계
            self.lanes.append({"laneID": lane["laneID"], "stop": (x0, y0),
                               "outer": (x1, y1), "heading": heading,
                               "signalGroup": sgs[0]})

    def to_xy(self, lat, lon):
        """위경도를 교차로 기준점에서의 동(x)·북(y) 미터로."""
        x = (lon - self.ref_lon) * M_PER_DEG_LAT * math.cos(math.radians(self.ref_lat))
        y = (lat - self.ref_lat) * M_PER_DEG_LAT
        return x, y

    def locate(self, lat, lon, heading):
        """내 차가 있는 진입 차로와 정지선까지 거리(m)를 찾는다. 없으면 None."""
        px, py = self.to_xy(lat, lon)
        best = None
        for ln in self.lanes:
            dh = abs((heading - ln["heading"] + 180) % 360 - 180)
            if dh > 45:
                continue                                     # 방향이 다르면 다른 차로
            (sx, sy), (ox, oy) = ln["stop"], ln["outer"]
            ux, uy = sx - ox, sy - oy
            length = math.hypot(ux, uy)
            ux, uy = ux / length, uy / length
            along = (px - ox) * ux + (py - oy) * uy           # 바깥쪽 끝에서 진행한 거리
            lateral = abs((px - ox) * uy - (py - oy) * ux)    # 차로 중심선에서 옆으로 벗어난 거리
            if lateral > 5 or along < -5 or along > length + 2:
                continue
            dist = length - along                            # 정지선까지 남은 거리
            if best is None or lateral < best[1]:
                best = (ln, lateral, dist)
        if best is None:
            return None
        return {"laneID": best[0]["laneID"], "signalGroup": best[0]["signalGroup"],
                "dist_to_stop": best[2]}


def spat_states(spat, intersection_id=None):
    """해석된 SPaT -> {signalGroup: (eventState, minEndTime(0.1초 단위 TimeMark))}"""
    out = {}
    for inter in spat["intersections"]:
        if intersection_id is not None and inter["id"]["id"] != intersection_id:
            continue
        for mv in inter["states"]:
            ev = mv["state-time-speed"][0]
            out[mv["signalGroup"]] = (ev["eventState"], ev.get("timing", {}).get("minEndTime"))
    return out
