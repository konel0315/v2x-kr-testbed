# V2X 가상환경 기본 구현 계획 (한국 기준, 기본만)

> 새 대화에서 이 문서를 먼저 붙여 넣고 시작한다. 1단계부터 순서대로 진행하고, 각 단계의 완료 기준을 통과해야 다음 단계로 간다.

## 0. 배경 (새 대화용 요약)

- 팀 프로젝트: 국내 C-ITS 환경을 전제로 V2X 통신 구조의 보안 요구사항을 설계하고, 오픈소스 가상환경에서 검증한다. 모듈(RSU, OBU, CA, 시뮬레이션)을 나눠 만들고 합친다.
- 이번 작업: **RSU 1대, OBU 2대, CA 서버 1대**로 가상환경을 만든다. **한국 기준의 기본 기능만** 넣는다. 팀이 제안한 추가 보안(재전송 검사, 속도 제한, 방화벽, 시각 교차 검사, SPaT 개연성 검사 등)은 **넣지 않는다.** 추가 보안은 이 기본 환경 위에 나중에 얹고, 켠 것과 끈 것을 비교한다.
- 원칙: 보내는 메시지는 전부 서명하고, 받은 메시지는 검증을 통과한 것만 쓴다.

### 한국 기준 (기본)

| 계층 | 기준 | 근거 | 가상환경에서 |
| --- | --- | --- | --- |
| 무선 | LTE-V2X | 과기정통부·국토부 2023.12 단일 방식 결정 | Docker 네트워크의 UDP 방송으로 대신 |
| 메시지 | SPaT, MAP, BSM (SAE J2735 계열) | KS R 1600 (산업부 보도자료 2023.6) | 그대로 |
| 서명 | IEEE 1609.2 | CTI 4001 p.66, 항법학회지 2023 | 그대로 (직접 구현) |
| 인증 체계 | SCMS 구조 | 자동차안전학회지 2021 | 단순화한 CA (아래 4절) |
| RSU 소프트웨어 | V2X-Hub (미국 교통부 FHWA) | V2X-Hub README | 메시지 생성·수신·기록에 사용 |

## 1. 범위

**한다**
- OBU 2대가 SUMO 차량 위치로 BSM을 만들고 서명해서 방송
- RSU가 BSM을 받아 서명 검증 후 통과한 것만 V2X-Hub로 전달
- RSU가 SPaT·MAP을 만들고 서명해서 방송, OBU가 받아 검증
- OBU가 검증을 통과한 SPaT로 자기 차 속도를 정함 (간단한 협력주행: 빨간불 정지, 초록불 통과)
- CA가 RSU·OBU에 인증서 발급 (루트 CA → 등록 CA → 응용 인증서 CA)
- 검증 항목: 서명, 권한(PSID), 유효기간, 발급 체인
- 메시지마다 처리 결과를 JSON 한 줄로 기록

**안 한다 (2차)**
- 재전송 검사, 속도 제한·큐 상한, iptables 방화벽, HTTPS 강제
- 시각 교차 검사, SPaT 개연성 검사, 위치 대조
- CRL(폐기 목록) 발행·적용 (시간이 남으면 7단계 뒤에 추가)
- 익명 인증서 교체, 키 HSM 보관, 인증서 자동 갱신

## 2. 전체 구조

```
SUMO (도로·차량·신호등)
   │ TraCI: 차량 위치/속도, 신호 상태
   ▼
   ▲ TraCI: 속도 명령 (협력주행)
OBU-1, OBU-2 (Python)                         CA 서버 (Python, REST)
 · BSM 생성 → 서명 → 방송                       · 루트/등록/응용 인증서 발급
 · SPaT·MAP 수신 → 검증 → 속도 결정             ▲ 발급 요청 (최초 1회)
   │  ▲                                          │
   │  │        가상 무선 (Docker 네트워크 UDP 방송)│
   ▼  │                                          │
┌─────────────────── RSU ─────────────────────────┐
│ 수신 게이트웨이 (Python): 검증 → 통과분만 전달  │
│        ▼                                        │
│ V2X-Hub (Docker)                                 │
│  · MessageReceiver (BSM 수신)                    │
│  · MAP / SPaT 생성                               │
│  · ImmediateForward → UDP 1516                   │
│  · JSON 로거                                     │
│        ▼                                        │
│ 송신 서명기 (Python): SPaT·MAP 서명 → 방송       │
└─────────────────────────────────────────────────┘
```

V2X-Hub는 메시지 처리기이고 서명을 하지 않는다. 그래서 **받는 쪽에 검증 게이트웨이, 보내는 쪽에 서명기**를 붙인다.

## 3. 사용 도구

| 역할 | 도구 | 비고 |
| --- | --- | --- |
| RSU 메시지 처리 | V2X-Hub (Docker, Apache 2.0) | https://github.com/usdot-fhwa-OPS/V2X-Hub . J2735 2016/2020/2024 선택 가능, 2024 사용 |
| 도로·차량 | SUMO + TraCI (Python) | 작은 교차로 1개, 신호등 1개, 차량 2대 |
| 1609.2 구조 | IEEE 1609.2 ASN.1 (ETSI Forge 공개본) | https://forge.etsi.org/rep/ITS/asn1/ieee1609.2 |
| ASN.1 인코딩 | Python `asn1tools` (OER 지원) | 1609.2는 OER 인코딩 |
| 서명 | Python `cryptography` (ECDSA P-256, SHA-256) | |
| 실행 묶음 | Docker Compose | 컨테이너: sumo, obu1, obu2, rsu-gateway, v2xhub, rsu-signer, ca |
| 대안 | fitsec2 (C) | 소스 빌드 가능 여부와 라이선스 미확인. Python이 막히면 검토 |

## 4. 단순화한 결정 (보고서에 명시할 것)

| 항목 | 실제 SCMS | 이번 구현 | 이유 |
| --- | --- | --- | --- |
| 인증서 형식 | 암시적 인증서가 기본 | **명시적 인증서** | 구현이 단순하고 1609.2가 둘 다 정의함 |
| 인증 기관 | RA, PCA, LA, MA 등 여러 기관 | 루트 CA, 등록 CA, 응용 CA 3개 | 기본 발급 흐름만 재현 |
| OBU 인증서 | 익명 인증서 여러 장, 주기 교체 | 1장 고정 | 교체는 2차 |
| 무선 | LTE-V2X PC5 | UDP 방송 | 물리 계층은 범위 밖 |
| 메시지 봉투 | IEEE 1609.3 WSMP | 간단한 헤더(PSID + 길이) | 상위 계층 구조만 유지 |

## 5. 단계별 계획

### 1단계. V2X-Hub 띄우고 BSM 수신 확인 (가장 먼저)
- V2X-Hub를 Docker로 실행, 웹 UI 접속
- MessageReceiver, MAP, ImmediateForward, JSON 로거 플러그인 활성화
- 서명 없는 샘플 BSM(UPER 인코딩)을 UDP로 MessageReceiver에 보냄
- **완료 기준**: JSON 로그에 BSM이 디코딩되어 찍힌다
- 확인할 것: MessageReceiver 수신 포트(팀 메모상 26789, 미확인), 플러그인 설정 방법
- **이 단계가 안 되면 멈추고 대안(Vanetza 등)을 다시 논의**

### 2단계. 가상 무선 + OBU 2대 (서명 없이)
- Docker 네트워크에 UDP 방송 채널 하나
- OBU 컨테이너 2개: SUMO TraCI로 자기 차량 위치·속도를 읽어 BSM을 10 Hz로 방송
- RSU 게이트웨이(지금은 검증 없이 통과)가 받아 V2X-Hub로 전달
- **완료 기준**: OBU 2대의 BSM이 V2X-Hub 로그에 차량별로 찍히고, 위치가 SUMO와 일치

### 3단계. RSU 송신 (서명 없이)
- MAP: 교차로 MAP 파일을 V2X-Hub MAP 플러그인에 등록
- SPaT: SUMO 신호등 상태로 만든다 (방법은 6절 결정 사항 참고)
- ImmediateForward 출력(UDP 1516)을 송신기가 받아 가상 무선으로 방송
- **완료 기준**: OBU 2대가 SPaT·MAP을 받아 디코딩하고, SPaT 신호가 SUMO 신호등과 일치

### 3-1단계. 간단한 협력주행
- SUMO의 신호 준수 기능을 끈다. 차는 SUMO 신호등을 직접 보지 않는다 (TraCI `setSpeedMode`로 신호 무시 설정)
- OBU가 **V2X로 받은 SPaT·MAP만 보고** 자기 차의 속도를 정해 TraCI `setSpeed`로 명령한다
  - MAP으로 자기 차로와 정지선 위치를 찾는다
  - 자기 차로의 신호가 빨간불이고 정지선까지 정지 가능한 거리면 감속해 정지선 앞에서 멈춘다
  - 초록불이면 제한속도로 통과한다
  - SPaT를 일정 시간(예: 1초) 못 받으면 안전하게 감속한다
- 6단계 이후에는 **검증을 통과한 SPaT만** 이 판단에 쓴다
- **완료 기준**: OBU가 V2X로 받은 신호만으로 빨간불에 멈추고 초록불에 출발한다. SUMO 화면에서 신호 위반이 없다
- 이 단계 덕분에 보안 효과가 눈에 보인다. 검증을 끄고 "모든 방향 초록불" SPaT를 넣으면 차가 신호를 위반하고, 검증을 켜면 멈춘다 (7단계 시험)

### 4단계. CA 서버
- 루트 CA(자체 서명) → 등록 CA → 응용 CA
- REST API: 등록 인증서 발급, 응용 인증서 발급, 인증서 체인 배포
- 응용 인증서 권한(PSID): RSU는 SPaT·MAP, OBU는 BSM
- 유효기간을 짧게도 발급할 수 있게 (만료 시험용)
- **완료 기준**: RSU 1, OBU 2가 기동 시 인증서를 받아 저장하고, 체인을 루트까지 따라갈 수 있다

### 5단계. 서명
- OBU: BSM을 1609.2 서명 데이터로 감싸 방송 (PSID, 생성 시각, 서명자 인증서, 서명)
- RSU 송신 서명기: SPaT·MAP을 같은 방식으로 서명 후 방송
- **완료 기준**: 방송되는 모든 패킷이 서명 데이터 형식이다 (패킷 캡처로 확인)

### 6단계. 검증
- RSU 게이트웨이와 OBU 수신부에 같은 검증 모듈 사용
- 검증 순서: ① 서명 ② 권한(PSID가 인증서에 있는가) ③ 유효기간(생성 시각과 현재 시각) ④ 발급 체인(신뢰하는 루트까지)
- 하나라도 실패하면 버리고 기록. 통과한 것만 V2X-Hub로 전달
- **완료 기준**: 아래 7단계 시험 통과

### 7단계. 기본 시험

| 시험 | 방법 | 기대 결과 |
| --- | --- | --- |
| 정상 | 전체 기동 | SPaT·MAP·BSM 모두 통과, 로그 ACCEPT |
| 위조 서명 | 서명 바이트 1개 변조 | 거부, BAD_SIGNATURE |
| 권한 없음 | OBU 인증서로 SPaT 서명 | 거부, NO_PERMISSION |
| 만료 | 유효기간 지난 인증서 | 거부, CERT_EXPIRED |
| 모르는 CA | 다른 루트가 발급한 인증서 | 거부, UNKNOWN_ISSUER |
| 가짜 신호 (검증 끔) | 공격자가 서명 없는 "모든 방향 초록불" SPaT 방송, OBU 검증 끔 | 차가 빨간불에 진입 (SUMO에서 신호 위반 확인) |
| 가짜 신호 (검증 켬) | 같은 공격, OBU 검증 켬 | 가짜 SPaT 거부, 차가 정지선 앞에서 멈춤 |

### (선택) 8단계. CRL
- CA가 CRL 발행, RSU·OBU가 주기적으로 받아 적용
- 시험: OBU 인증서 폐기 후 그 OBU의 BSM이 거부되는지

## 6. 시작 전에 정할 것

1. **실행 환경**: 본인 PC(Linux 또는 WSL2 + Docker)인지 학교 서버인지
2. **CA 담당**: CA가 B 담당이면 이번에는 간단한 임시 CA를 만들고 나중에 B의 것으로 교체. 인터페이스(REST 주소, 인증서 파일 형식)는 B와 맞춘다
3. **J2735 인코더**: J2735 ASN.1 원본은 SAE 유료다. V2X-Hub 안에 들어 있는 J2735 코덱을 꺼내 쓸 수 있는지 1단계에서 확인. 안 되면 대안 탐색
4. **SPaT 만드는 방법**: V2X-Hub SPaT 플러그인은 실제 신호제어기와 NTCIP 1202(SNMP)로 통신한다. 가상 신호제어기를 만들지, SUMO 신호 상태로 SPaT를 직접 만들어 V2X-Hub에 넣을지 3단계 전에 결정
5. **PSID 값**: BSM, SPaT, MAP의 PSID를 IEEE 1609.12 기준으로 확인하고 OBU 담당과 맞춘다

## 7. 공통 로그 형식 (메시지당 한 줄)

```json
{
  "traffic": {"message_id": "...", "message_type": "BSM", "sender_id": "OBU-02", "received_at": "2026-11-17T09:00:00.123Z"},
  "auth": {"auth_status": "VALID", "fail_step": null},
  "checks": {"decode_status": "VALID", "semantic_status": "NOT_CHECKED"},
  "result": {"decision": "ACCEPT", "reason": "NONE"},
  "meta": {"processing_time_ms": 1.2, "node": "RSU-01", "process_state": "RUNNING"}
}
```

- fail_step: 1 서명, 2 권한, 3 유효기간, 4 발급 체인
- 기본 구현에서 semantic_status는 항상 NOT_CHECKED (의미 검사는 2차)

## 8. 참고 링크

- V2X-Hub: https://github.com/usdot-fhwa-OPS/V2X-Hub
- IEEE 1609.2 ASN.1: https://forge.etsi.org/rep/ITS/asn1/ieee1609.2
- 팀 문서 KR-RSU v0.1: https://claude.ai/artifact/1Y2wyZeHASgPbAY6HvG9fK
