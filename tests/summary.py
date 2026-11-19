"""logs/*.jsonl 을 읽어 노드별로 결정(ACCEPT/REJECT)과 이유를 센다. 7단계 결과표용.

사용법: python3 tests/summary.py [--since 초]   (최근 N초만 보기, 기본 전체)
"""
import argparse
import glob
import json
import os
from collections import Counter
from datetime import datetime, timezone


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=float, default=None)
    args = ap.parse_args()
    now = datetime.now(timezone.utc)
    for path in sorted(glob.glob("logs/*.jsonl")):
        c = Counter()
        for line in open(path):
            r = json.loads(line)
            if args.since:
                t = datetime.fromisoformat(r["traffic"]["received_at"])
                if (now - t).total_seconds() > args.since:
                    continue
            key = (r["traffic"]["message_type"], r["result"]["decision"], r["result"]["reason"],
                   r["auth"]["fail_step"])
            c[key] += 1
        if c:
            print(f"== {os.path.basename(path)}")
            for (mt, d, reason, step), n in sorted(c.items(), key=lambda x: -x[1]):
                print(f"   {mt:6s} {d:20s} {reason:15s} fail_step={step}  {n}개")


if __name__ == "__main__":
    main()
