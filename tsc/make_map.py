"""SUMO 도로망으로 J2735 MAP을 만든다 (V2X-Hub MapPlugin에 넣을 UPER hex 파일).

사용법:
    python3 tsc/make_map.py --net sumo/intersection.net.xml --out ~/v2xhub_data/download/MAP/pangyo_map.txt

교차로 1개(신호등 'C')의 진입 차로 4개와 진출 차로 4개를 담는다.
진입 차로 노드 0 = 정지선, 노드 1 = 차로 바깥쪽 끝.
"""
import argparse
import json
import os
import sys

import sumolib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import j2735  # noqa: E402

INTERSECTION_ID = 1
# 진입 도로 -> (진입 차로 ID, 진입 approach ID, 직진해서 나가는 차로 ID, 신호 그룹)
INGRESS = {"W2C": (1, 1, 6, 2), "S2C": (3, 2, 8, 4), "E2C": (5, 3, 2, 6), "N2C": (7, 4, 4, 8)}
EGRESS = {"C2W": 2, "C2S": 4, "C2E": 6, "C2N": 8}


def node(dx_m, dy_m):
    """이전 점에서의 차이(m)를 가장 작은 J2735 노드 형식으로."""
    x, y = int(round(dx_m * 100)), int(round(dy_m * 100))
    for kind, lim in (("node-XY1", 511), ("node-XY2", 1023), ("node-XY3", 2047),
                      ("node-XY4", 4095), ("node-XY5", 8191), ("node-XY6", 32767)):
        if abs(x) <= lim and abs(y) <= lim:
            return {"delta": (kind, {"x": x, "y": y})}
    raise ValueError("노드 간격이 너무 큼")


def node_list(points, ref):
    out, prev = [], ref
    for p in points:
        out.append(node(p[0] - prev[0], p[1] - prev[1]))
        prev = p
    return ("nodes", out)


def build(net_file):
    net = sumolib.net.readNet(net_file)
    junction = net.getNode("C")
    cx, cy = junction.getCoord()
    ref_lon, ref_lat = net.convertXY2LonLat(cx, cy)
    lanes = []
    for edge_id, (lane_id, appr, out_lane, sg) in INGRESS.items():
        shape = net.getEdge(edge_id).getLane(0).getShape()
        pts = [shape[-1], shape[0]]                     # 정지선 -> 바깥쪽
        lanes.append({
            "laneID": lane_id, "ingressApproach": appr,
            "laneAttributes": {"directionalUse": (0b10, 2), "sharedWith": (0, 10),
                               "laneType": ("vehicle", (0, 8))},
            "maneuvers": (0b100000000000, 12),            # 직진만 허용
            "nodeList": node_list(pts, (cx, cy)),
            "connectsTo": [{"connectingLane": {"lane": out_lane,
                                               "maneuver": (0b100000000000, 12)},
                            "signalGroup": sg}],
        })
    for edge_id, lane_id in EGRESS.items():
        shape = net.getEdge(edge_id).getLane(0).getShape()
        pts = [shape[0], shape[-1]]                     # 교차로 쪽 -> 바깥쪽
        lanes.append({
            "laneID": lane_id,
            "laneAttributes": {"directionalUse": (0b01, 2), "sharedWith": (0, 10),
                               "laneType": ("vehicle", (0, 8))},
            "nodeList": node_list(pts, (cx, cy)),
        })
    map_data = {
        "msgIssueRevision": 1,
        "intersections": [{
            "name": "Pangyo-Virtual-1",
            "id": {"id": INTERSECTION_ID}, "revision": 1,
            "refPoint": {"lat": int(round(ref_lat * 1e7)), "long": int(round(ref_lon * 1e7))},
            "laneWidth": 320,                                  # cm
            "laneSet": lanes,
        }],
    }
    return map_data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--net", default="sumo/intersection.net.xml")
    ap.add_argument("--out", required=True, help="UPER hex 텍스트 파일 경로 (.txt)")
    args = ap.parse_args()
    map_data = build(args.net)
    frame = j2735.encode_frame(j2735.MAP_ID, "MapData", map_data)
    out = os.path.expanduser(args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        f.write(frame.hex().upper())
    print(f"MAP {len(frame)}바이트 -> {out}")
    # 사람이 읽을 수 있는 사본
    j2735.decode(frame)
    print(json.dumps({"refPoint": map_data["intersections"][0]["refPoint"],
                      "lanes": len(map_data["intersections"][0]["laneSet"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
