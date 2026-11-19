"""가상 무선 채널 접속기.

LTE-V2X 무선 대신, radio/air.py(가상 공중)에 UDP로 붙는다.
send()로 보낸 WSM은 같은 채널의 다른 모든 노드에게 전달된다(방송).
"""
import socket
import time

AIR = ("127.0.0.1", 47000)


class Radio:
    def __init__(self, name, air=AIR):
        self.name = name
        self.air = air
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.setblocking(False)
        self._last_join = 0.0
        self._join()

    def _join(self):
        # 1초마다 '나 여기 있다'를 알려 채널에 등록 상태를 유지
        self.sock.sendto(b"JOIN " + self.name.encode(), self.air)
        self._last_join = time.monotonic()

    def send(self, wsm):
        if time.monotonic() - self._last_join > 1.0:
            self._join()
        self.sock.sendto(wsm, self.air)

    def recv_all(self):
        """지금까지 들어온 WSM을 모두 꺼낸다 (기다리지 않음)."""
        if time.monotonic() - self._last_join > 1.0:
            self._join()
        out = []
        while True:
            try:
                data, _ = self.sock.recvfrom(65535)
            except BlockingIOError:
                return out
            out.append(data)

    def recv(self, timeout=None):
        """WSM 하나를 기다려 받는다. timeout초 동안 없으면 None."""
        self.sock.settimeout(timeout)
        try:
            data, _ = self.sock.recvfrom(65535)
            return data
        except socket.timeout:
            return None
        finally:
            self.sock.setblocking(False)
            if time.monotonic() - self._last_join > 1.0:
                self._join()
