"""가상 공중(무선 채널). LTE-V2X PC5 방송을 흉내 낸다.

노드들이 UDP 47000으로 'JOIN 이름'을 보내 채널에 붙고,
그 외의 패킷은 보낸 노드를 뺀 모든 노드에게 그대로 전달한다.
3초 동안 소식이 없는 노드는 채널에서 뺀다.

사용법: python3 radio/air.py [--loss 0.0] [--delay-ms 0]
  --loss, --delay-ms: 무선 손실·지연 흉내 (기본 0, 2차 시험용)
"""
import argparse
import random
import socket
import threading
import time

PORT = 47000
TIMEOUT = 3.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loss", type=float, default=0.0, help="패킷 손실 확률 (0~1)")
    ap.add_argument("--delay-ms", type=float, default=0.0, help="전달 지연 (ms)")
    args = ap.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", PORT))
    nodes = {}   # addr -> (이름, 마지막 소식 시각)
    count = 0
    print(f"[air] 가상 무선 채널 시작 (UDP {PORT}, 손실 {args.loss}, 지연 {args.delay_ms}ms)")

    def deliver(data, to):
        if args.delay_ms > 0:
            time.sleep(args.delay_ms / 1000)
        sock.sendto(data, to)

    last_report = time.monotonic()
    while True:
        data, addr = sock.recvfrom(65535)
        now = time.monotonic()
        if data.startswith(b"JOIN "):
            name = data[5:].decode(errors="replace")
            if addr not in nodes:
                print(f"[air] 접속: {name} {addr[1]}")
            nodes[addr] = (name, now)
            continue
        if addr in nodes:
            nodes[addr] = (nodes[addr][0], now)
        for a in [a for a, (_, t) in nodes.items() if now - t > TIMEOUT]:
            print(f"[air] 끊김: {nodes.pop(a)[0]}")
        for a in nodes:
            if a == addr or random.random() < args.loss:
                continue
            if args.delay_ms > 0:
                threading.Thread(target=deliver, args=(data, a), daemon=True).start()
            else:
                sock.sendto(data, a)
        count += 1
        if now - last_report > 10:
            print(f"[air] 노드 {len(nodes)}개, 누적 전달 {count}개")
            last_report = now


if __name__ == "__main__":
    main()
