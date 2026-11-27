"""가상 교통센터(TMC): 상용 휴대폰망(V2N)으로 차량과 주고받는 서버.

  - 차량 → 센터: 차량이 휴대폰망으로 올린 BSM(위치 보고)을 IEEE 1609.2로 검증하고 모은다.
  - 센터 → 차량: 공사 구간 안내 TIM(KS R 1600-5)을 TMC-01 인증서(PSID 0x8003)로 서명해서
                 1초마다 휴대폰망으로 내려보낸다.
  - 하이브리드(V2X + V2N, 국토부 C-ITS 구축 방침): 같은 서명된 TIM을 RSU에도 넘겨
                 RSU 근처 차량은 직접통신(V2X)으로도 받게 한다. RSU는 서명을 확인한 뒤 그대로 방송한다.
  - 휴대폰망 구간은 TLS 1.3 (common/v2n.py).

사용법: python3 center/center.py [--zone-north 70 --radius 40 --speed 30] [--no-rsu]
  공사 구간: 교차로 중심에서 북쪽 --zone-north m 지점, 반지름 --radius m, 권고 속도 --speed km/h
"""
import argparse
import os
import socket
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import geo, j2735, psid, sec1609, v2n, wsmp  # noqa: E402
from common.identity import Identity  # noqa: E402
from common.v2xlog import V2XLog  # noqa: E402

CENTER_LAT, CENTER_LON = 37.40000, 127.11000     # 교차로 중심 (sumo/intersection.nod.xml)
RSU_FORWARD = ("127.0.0.1", 1517)                # RSU가 '이미 서명된 메시지'를 받는 포트


class Center:
    def __init__(self, ident, log):
        self.ident = ident
        self.log = log
        self.clients = {}            # 소켓 -> 주소
        self.lock = threading.Lock()
        self.vehicles = {}           # 인증서 번호 -> (위도, 경도, 속도, 받은 시각)
        self.rejected = {}
        self.reports = 0

    # ---------------- 차량 연결 하나 (TLS)
    def serve_client(self, sock, addr):
        with self.lock:
            self.clients[sock] = addr
        print(f"[TMC] 차량 단말 연결: {addr[0]}:{addr[1]} ({sock.version()})")
        try:
            while True:
                wsm = v2n.recv_frame(sock)
                if wsm is None:
                    break
                self.on_uplink(wsm)
        except (OSError, ValueError):
            pass
        finally:
            with self.lock:
                self.clients.pop(sock, None)
            sock.close()
            print(f"[TMC] 차량 단말 연결 끊김: {addr[0]}:{addr[1]}")

    def on_uplink(self, wsm):
        t0 = time.perf_counter()
        try:
            p, data = wsmp.decode(wsm)
        except ValueError:
            return
        if p != psid.BSM:
            return
        try:
            if not sec1609.is_spdu(data):
                raise sec1609.VerifyError(1, "UNSIGNED")
            data, cert = self.ident.verifier.verify(data, psid.BSM)
        except sec1609.VerifyError as e:
            self.rejected[e.reason] = self.rejected.get(e.reason, 0) + 1
            self.log.write("BSM(V2N)", "?", "REJECT", e.reason, auth_status="INVALID",
                           fail_step=e.step, t_start=t0)
            return
        _, bsm = j2735.decode(data)
        c = bsm["coreData"]
        self.vehicles[cert.name] = (c["lat"] / 1e7, c["long"] / 1e7, c["speed"] * 0.02, time.time())
        self.reports += 1
        self.log.write("BSM(V2N)", cert.name, "ACCEPT", auth_status="VALID", t_start=t0)

    # ---------------- 내려보내기
    def broadcast(self, wsm):
        with self.lock:
            socks = list(self.clients)
        for s in socks:
            try:
                v2n.send_frame(s, wsm)
            except OSError:
                pass
        return len(socks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zone-north", type=float, default=70.0, help="공사 구간 중심: 교차로에서 북쪽으로 m")
    ap.add_argument("--radius", type=float, default=40.0, help="공사 구간 반지름 m")
    ap.add_argument("--speed", type=float, default=30.0, help="권고 속도 km/h")
    ap.add_argument("--no-rsu", action="store_true", help="RSU로 넘기지 않음 (휴대폰망으로만)")
    args = ap.parse_args()

    ident = Identity("TMC-01")                       # SCMS 인증서 준비 (TIM 권한)
    log = V2XLog("TMC-01")
    center = Center(ident, log)
    zone_lat = CENTER_LAT + args.zone_north / geo.M_PER_DEG_LAT
    zone_lon = CENTER_LON

    ctx = v2n.server_context()
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(v2n.CENTER)
    srv.listen()
    print(f"[TMC] 교통센터 시작: 휴대폰망(TLS 1.3) {v2n.CENTER[0]}:{v2n.CENTER[1]}, "
          f"인증서 PSID {[hex(p) for p in ident.cert.psids]}")
    print(f"[TMC] 공사 구간 안내: 교차로 북쪽 {args.zone_north:.0f}m, 반지름 {args.radius:.0f}m, "
          f"권고 {args.speed:.0f} km/h" + ("" if args.no_rsu else f" (RSU {RSU_FORWARD[1]}에도 전달)"))

    def accept_loop():
        while True:
            raw, addr = srv.accept()
            try:
                s = ctx.wrap_socket(raw, server_side=True)
            except (OSError, ValueError) as e:
                print(f"[TMC] TLS 연결 실패 {addr}: {e}")
                raw.close()
                continue
            threading.Thread(target=center.serve_client, args=(s, addr), daemon=True).start()
    threading.Thread(target=accept_loop, daemon=True).start()

    rsu = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    msg_cnt, packet_id, last_report = 0, b"TMC-WZ-01", time.monotonic()
    start = time.time()
    while True:
        t0 = time.perf_counter()
        msg_cnt = (msg_cnt + 1) % 128
        tim = j2735.make_tim(msg_cnt, packet_id, zone_lat, zone_lon, args.radius, args.speed,
                             duration_min=120, start=start)
        wsm = wsmp.encode(psid.TIM, ident.sign(tim, psid.TIM))         # 센터가 서명
        n = center.broadcast(wsm)
        if not args.no_rsu:
            rsu.sendto(wsm, RSU_FORWARD)
        log.write("TIM", "TMC-01", "SENT", auth_status="SIGNED", t_start=t0)
        if time.monotonic() - last_report > 5:
            near = ", ".join(f"{k[:8]} {v[2]:.1f}m/s" for k, v in center.vehicles.items()
                             if time.time() - v[3] < 3)
            print(f"[TMC] 연결 차량 {n}대 | 받은 위치 보고 {center.reports} | 최근 차량: {near or '-'}"
                  + (f" | 거부 {center.rejected}" if center.rejected else ""))
            last_report = time.monotonic()
        time.sleep(1.0)


if __name__ == "__main__":
    main()
