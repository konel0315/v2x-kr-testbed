"""PSID (메시지 종류 번호). V2X-Hub 코드(TmxApiMessages.h), IEEE PSID 등록부, IEEE 1609.2.1의 값을 따른다.
값은 V2X-Hub·RSU 4.1과 같이 p-encoded 표기다."""
BSM = 0x20            # 차량 안전 메시지 (V2V, V2I)
SECURITY_MGMT = 0x23  # IEEE 1609.2.1 SecurityMgmtPsid (SCMS 인증서 관리 메시지)
PSM = 0x27            # 보행자 등 취약 도로 사용자 안전 (V2P, SAE J3268)
SPAT = 0x8002         # 신호 정보
TIM = 0x8003          # 여행자 정보 (공사·안내, V2N)
MAP = 0xE0000017      # 교차로 지도

NAMES = {BSM: "BSM", PSM: "PSM", SPAT: "SPAT", TIM: "TIM", MAP: "MAP"}
