# 4~6단계: CA, IEEE 1609.2 서명·검증

> 이 단계의 자체 CA(`ca/ca.py`)는 8단계에서 **OpenSCMS(IEEE 1609.2.1)** 로 바뀌었고 저장소에서 지웠다. 서명·검증 4단계는 그대로다. 지금 구성: [openscms.md](openscms.md)

모든 메시지(BSM·SPaT·MAP)는 IEEE 1609.2로 서명되고, 받는 쪽(RSU 게이트웨이, OBU)은 검증을 통과한 것만 쓴다.

## 구성
| 모듈 | 파일 | 역할 |
| --- | --- | --- |
| CA | ca/ca.py | 루트 CA → 등록 CA(ECA)·응용 CA(ACA). 등록 인증서 발급(/enroll), 등록 인증서로 서명된 요청을 검증해 응용 인증서 발급(/app-cert), 체인 배포(/chain). 등록된 장치(RSU-01, OBU-01, OBU-02)만 허용. 권한은 CA가 장치 종류로 정함: OBU=BSM(0x20), RSU=SPaT(0x8002)·MAP(0xE0000017) |
| 1609.2 | common/sec1609.py | 명시적 인증서, SignedData(서명자 인증서 포함), 검증 4단계. COER 인코딩, ECDSA P-256/SHA-256 |
| 장치 인증서 | common/identity.py | 시작 시 키 생성 → 등록 인증서 → 응용 인증서, CA 체인으로 검증기 생성 |
| RSU 서명기 | rsu-signer/signer.py | V2X-Hub 출력 SPaT·MAP을 서명해 방송 |
| RSU 게이트웨이 | rsu-gateway/gateway.py | BSM 검증, 통과분만 V2X-Hub로 |
| OBU | obu/obu.py | BSM 서명·방송, SPaT·MAP 검증 후 사용 |

## 인증서 발급 흐름
1. CA는 처음 실행할 때 루트·ECA·ACA 키와 인증서를 만들어 ca/data/에 보관한다 (Git 제외)
2. 장치는 시작할 때 공개키를 보내 등록 인증서를 받는다 (/enroll)
3. 등록 인증서로 서명한 요청을 보내 응용 인증서를 받는다 (/app-cert, 요청 PSID 0x23)
4. CA 체인(루트·ECA·ACA)을 받아 신뢰 저장소로 쓴다 (/chain)

## 서명
서명 입력: SHA256( SHA256(tbsData COER) ‖ SHA256(서명자 인증서 COER) ), ECDSA P-256.
SPDU = Ieee1609Dot2Data { protocolVersion 3, signedData { tbsData { J2735 MessageFrame, psid, generationTime }, signer = 인증서, signature } }

## 검증 순서 (로그의 fail_step)
1. 서명: 서명이 없으면 UNSIGNED, 틀리면 BAD_SIGNATURE
2. 권한: headerInfo.psid가 인증서 appPermissions에 있고 WSMP PSID와 같은가 → NO_PERMISSION
3. 유효기간: 생성 시각과 현재 시각이 인증서 기간 안인가 → CERT_EXPIRED
4. 발급 체인: 발급자 HashedId8로 ACA → 루트까지 서명·기간 확인 → UNKNOWN_ISSUER

## 성능 (참고)
서명 약 0.3 ms, 검증 약 0.8 ms (Python). 서명된 BSM 약 233 B (서명자 인증서 포함).

## 단순화한 점
- 명시적 인증서 (실제 SCMS는 암시적 인증서가 기본)
- 기관: 루트·ECA·ACA 3개 (실제는 RA, PCA, LA, MA 등)
- OBU 인증서 1장 고정, 익명 인증서 교체 없음
- 매 메시지에 서명자 인증서 전체 포함 (실제는 대부분 digest로 줄임)
- 인증서 요청 PSID 0x23은 이 프로젝트에서 정한 값
- CA 통신은 HTTP, 키는 파일·메모리
- 재전송 검사, 속도 제한, CRL 등은 2차 과제
