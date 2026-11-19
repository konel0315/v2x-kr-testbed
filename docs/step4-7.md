# 4~7단계: CA, IEEE 1609.2 서명·검증, 기본 보안 시험

## 결과 요약
모든 메시지(BSM·SPaT·MAP)는 IEEE 1609.2로 서명되고, 받는 쪽(RSU 게이트웨이, OBU)은 검증을 통과한 것만 쓴다.
7단계 시험 7개가 모두 기대 결과와 같다.

| 시험 | 방법 | 기대 결과 | 결과 |
| --- | --- | --- | --- |
| 정상 | `bash scripts/run.sh --coop` | 모두 ACCEPT | SPaT·MAP·BSM 전부 ACCEPT, 거부 0, 신호 위반 0 |
| 위조 서명 | `tests/attack.py --mode tamper` (진짜 SPaT를 가로채 초록불로 변조, 서명은 그대로) | BAD_SIGNATURE | 가짜 전부 REJECT BAD_SIGNATURE (fail_step 1), 위반 0 |
| 권한 없음 | `tests/attack.py --mode no-permission` (BSM 권한뿐인 OBU 인증서로 SPaT 서명) | NO_PERMISSION | 전부 REJECT NO_PERMISSION (fail_step 2), 위반 0 |
| 만료 | `bash scripts/run.sh --coop --rsu-cert 25` (RSU 인증서 25초) | CERT_EXPIRED | 만료 후 RSU SPaT·MAP 전부 REJECT CERT_EXPIRED (fail_step 3). 차는 신호 UNKNOWN으로 정지 유지 |
| 모르는 CA | `tests/attack.py --mode unknown-ca` (공격자가 만든 루트 CA) | UNKNOWN_ISSUER | 전부 REJECT UNKNOWN_ISSUER (fail_step 4), 위반 0 |
| 가짜 신호 (검증 끔) | `--coop --no-verify` + `--mode unsigned` | 차가 빨간불에 진입 | **신호 위반 1회**: 실제 신호 'r'에서 진입, OBU는 GREEN으로 봄 |
| 가짜 신호 (검증 켬) | `--coop` + `--mode unsigned` | 가짜 거부, 정지 | 전부 REJECT UNSIGNED (fail_step 1), 정지선 2.1 m 앞 정지, 위반 0 |

공격은 초당 100개(진짜 RSU의 10배)로 "모든 방향 초록불" SPaT를 방송한다.
(위 결과는 V2X-Hub 흉내(--mock)로 측정. 실제 V2X-Hub에서도 같은 방법으로 재현한다.)

## 구성
| 모듈 | 파일 | 역할 |
| --- | --- | --- |
| CA | ca/ca.py | 루트 CA → 등록 CA(ECA)·응용 CA(ACA). 등록 인증서 발급(/enroll), 등록 인증서로 서명된 요청을 검증해 응용 인증서 발급(/app-cert), 체인 배포(/chain). 권한은 CA가 장치 종류로 정함: OBU=BSM(0x20), RSU=SPaT(0x8002)·MAP(0xE0000017) |
| 1609.2 | common/sec1609.py | 명시적 인증서, SignedData(서명자 인증서 포함), 검증 4단계. COER 인코딩, ECDSA P-256/SHA-256 |
| 장치 인증서 | common/identity.py | 시작 시 키 생성 → 등록 인증서 → 응용 인증서, CA 체인으로 검증기 생성 |
| RSU 서명기 | rsu-signer/signer.py | V2X-Hub 출력 SPaT·MAP을 서명해 방송 |
| RSU 게이트웨이 | rsu-gateway/gateway.py | BSM 검증, 통과분만 V2X-Hub로 |
| OBU | obu/obu.py | BSM 서명·방송, SPaT·MAP 검증 후 사용, 신호 위반 감지 |
| 시험 | tests/attack.py, tests/summary.py | 공격 방송, 로그 집계 |

## 검증 순서 (fail_step)
1. 서명: 서명자 인증서의 공개키로 SHA256(SHA256(tbsData) ‖ SHA256(인증서)) 서명 확인. 서명 없으면 UNSIGNED, 틀리면 BAD_SIGNATURE
2. 권한: headerInfo.psid가 인증서 appPermissions에 있고 WSMP PSID와 같은가 → NO_PERMISSION
3. 유효기간: 생성 시각과 현재 시각이 인증서 기간 안인가 → CERT_EXPIRED
4. 발급 체인: 발급자 HashedId8로 ACA → 루트까지 서명·기간 확인 → UNKNOWN_ISSUER

## 성능 (참고)
서명 약 0.3 ms, 검증 약 0.8 ms (Python, pycrate + cryptography). SPDU 크기: BSM 약 233 B (서명자 인증서 포함).

## 단순화한 점 (계획서 4절)
- 명시적 인증서 (실제 SCMS는 암시적 인증서가 기본)
- 기관: 루트·ECA·ACA 3개 (실제는 RA, PCA, LA, MA 등)
- OBU 인증서 1장 고정, 익명 인증서 교체 없음
- 매 메시지에 서명자 인증서 전체 포함 (실제는 대부분 digest로 줄임)
- 인증서 요청 PSID 0x23은 이 프로젝트에서 정한 값
- CA 통신은 HTTP (HTTPS는 2차), 키는 파일·메모리 (HSM은 2차)
- 재전송 검사, 속도 제한, CRL은 2차

## 안전 동작
- MAP 수신 전에는 V2X 주행을 시작하지 않음
- SPaT가 1초 넘게 없거나 모두 거부되면 신호 UNKNOWN → 감속·정지
