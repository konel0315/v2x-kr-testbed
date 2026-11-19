"""PSID (메시지 종류 번호). V2X-Hub 코드(TmxApiMessages.h)의 값을 따른다."""
BSM = 0x20
CERT_REQUEST = 0x23   # 이 프로젝트에서 인증서 요청 메시지에 쓰는 PSID (SCMS 인증서 관리용으로 가정)
SPAT = 0x8002
MAP = 0xE0000017

NAMES = {BSM: "BSM", SPAT: "SPAT", MAP: "MAP"}
