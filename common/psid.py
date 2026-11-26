"""PSID (메시지 종류 번호). V2X-Hub 코드(TmxApiMessages.h)와 IEEE 1609.2.1의 값을 따른다."""
BSM = 0x20
SECURITY_MGMT = 0x23  # IEEE 1609.2.1 SecurityMgmtPsid (SCMS 인증서 관리 메시지)
SPAT = 0x8002
MAP = 0xE0000017

NAMES = {BSM: "BSM", SPAT: "SPAT", MAP: "MAP"}
