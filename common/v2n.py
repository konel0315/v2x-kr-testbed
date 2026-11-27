"""V2N(차량 ↔ 네트워크) 연결: 상용 휴대폰망(LTE Uu)을 거쳐 교통센터와 주고받는 경로.

실제로는 휴대폰망과 인터넷을 지나지만, 여기서는 내 PC 안의 TCP 연결로 흉내 낸다.
  - 전송 구간: TLS 1.3 (TTAK.KO-12.0432: 관제센터는 TLS 보안 채널). 센터 인증서는 시험용 TLS CA가 발급.
  - 내용: V2X와 같은 IEEE 1609.2 서명 메시지를 그대로 실어 보낸다. 받는 쪽은 V2X와 똑같이 검증한다.
    (휴대폰망을 지나도 메시지 서명을 유지: 5GAA Uu 프로파일과 같은 방식)
  - 한 덩어리 = [길이 4바이트][WSMP(PSID + 1609.2 메시지)]

TLS 인증서·키는 center/tls/ 에 처음 실행할 때 만든다 (Git 제외).
"""
import datetime
import ipaddress
import os
import queue
import socket
import ssl
import struct
import threading
import time

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TLS_DIR = os.environ.get("V2N_TLS_DIR", os.path.join(ROOT, "center", "tls"))
CENTER = (os.environ.get("V2N_HOST", "127.0.0.1"), int(os.environ.get("V2N_PORT", "9443")))
SERVER_NAME = "tmc.v2x.local"          # 센터 TLS 인증서의 이름 (클라이언트가 확인)


# ------------------------------------------------------------ TLS 인증서 (시험용)
def _write(path, data, secret=False):
    with open(path, "wb") as f:
        f.write(data)
    if secret:
        os.chmod(path, 0o600)


def ensure_tls():
    """시험용 TLS CA와 교통센터 서버 인증서가 없으면 만든다. → (ca.pem, server.pem, server.key)"""
    ca_p, crt_p, key_p = (os.path.join(TLS_DIR, f) for f in ("ca.pem", "server.pem", "server.key"))
    if all(os.path.exists(p) for p in (ca_p, crt_p, key_p)):
        return ca_p, crt_p, key_p
    os.makedirs(TLS_DIR, exist_ok=True)
    now = datetime.datetime.now(datetime.timezone.utc)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "V2X Testbed TLS CA")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
          .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now - datetime.timedelta(minutes=5))
          .not_valid_after(now + datetime.timedelta(days=365))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False,
                                       key_encipherment=False, data_encipherment=False,
                                       key_agreement=False, key_cert_sign=True, crl_sign=True,
                                       encipher_only=False, decipher_only=False), critical=True)
          .sign(ca_key, hashes.SHA256()))
    key = ec.generate_private_key(ec.SECP256R1())
    crt = (x509.CertificateBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, SERVER_NAME)]))
           .issuer_name(ca_name).public_key(key.public_key())
           .serial_number(x509.random_serial_number())
           .not_valid_before(now - datetime.timedelta(minutes=5))
           .not_valid_after(now + datetime.timedelta(days=365))
           .add_extension(x509.SubjectAlternativeName([
               x509.DNSName(SERVER_NAME), x509.DNSName("localhost"),
               x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
           .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
           .sign(ca_key, hashes.SHA256()))
    _write(ca_p, ca.public_bytes(serialization.Encoding.PEM))
    _write(crt_p, crt.public_bytes(serialization.Encoding.PEM))
    _write(key_p, key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption()), secret=True)
    return ca_p, crt_p, key_p


def server_context():
    _, crt, key = ensure_tls()
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.load_cert_chain(crt, key)
    return ctx


def client_context():
    ca = os.path.join(TLS_DIR, "ca.pem")
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)          # 서버 인증서·이름 확인 켜짐
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.load_verify_locations(ca)
    return ctx


# ------------------------------------------------------------ 덩어리 주고받기
def send_frame(sock, wsm):
    sock.sendall(struct.pack(">I", len(wsm)) + wsm)


def recv_frame(sock):
    """한 덩어리를 받는다. 연결이 끊기면 None."""
    head = _recv_exact(sock, 4)
    if head is None:
        return None
    n = struct.unpack(">I", head)[0]
    if n > 65535:
        raise ValueError("덩어리가 너무 큼")
    return _recv_exact(sock, n)


def _recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


# ------------------------------------------------------------ 차량 쪽 (휴대폰 모뎀)
class V2NClient:
    """뒤에서 교통센터에 TLS로 붙어 있는 휴대폰 모뎀.
    send()로 올린 메시지는 센터로 가고, 센터가 보낸 메시지는 recv_all()로 꺼낸다.
    센터가 꺼져 있으면 2초마다 다시 붙는다."""

    def __init__(self, name, center=CENTER):
        self.name = name
        self.center = center
        self.inbox = queue.Queue()
        self.outbox = queue.Queue(maxsize=100)
        self.connected = False
        self._stop = False
        threading.Thread(target=self._run, daemon=True).start()

    def send(self, wsm):
        try:
            self.outbox.put_nowait(wsm)
        except queue.Full:
            pass                                    # 연결이 끊겨 쌓이면 오래된 것부터 버림

    def recv_all(self):
        out = []
        while True:
            try:
                out.append(self.inbox.get_nowait())
            except queue.Empty:
                return out

    def close(self):
        self._stop = True

    def _run(self):
        while not self._stop:
            try:
                if not os.path.exists(os.path.join(TLS_DIR, "ca.pem")):
                    raise ConnectionError("센터 TLS CA가 아직 없음")
                raw = socket.create_connection(self.center, timeout=3)
                sock = client_context().wrap_socket(raw, server_hostname=SERVER_NAME)
                sock.settimeout(0.2)
                self.connected = True
                print(f"[{self.name}] V2N: 교통센터 연결됨 ({sock.version()})")
                self._loop(sock)
            except (OSError, ssl.SSLError, ConnectionError, ValueError):
                pass
            if self.connected:
                print(f"[{self.name}] V2N: 교통센터 연결 끊김, 다시 연결 시도")
            self.connected = False
            time.sleep(2)

    def _loop(self, sock):
        head = b""
        while not self._stop:
            while not self.outbox.empty():
                send_frame(sock, self.outbox.get_nowait())
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    return
                head += chunk
            except (socket.timeout, ssl.SSLWantReadError):
                continue
            while len(head) >= 4:
                n = struct.unpack(">I", head[:4])[0]
                if len(head) < 4 + n:
                    break
                self.inbox.put(head[4:4 + n])
                head = head[4 + n:]
