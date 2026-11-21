# V2X 가상환경 (한국 C-ITS 기준) — RSU 1, OBU 2, CA 1

국내 C-ITS 표준을 전제로 V2X 통신의 기본 보안(IEEE 1609.2 서명·검증)을 오픈소스 가상환경에서 구현하고 검증한다.
모든 메시지는 서명되고, 받는 쪽은 검증을 통과한 메시지만 쓴다.

## 한국 기준과 구현

| 계층 | 기준 | 근거 | 이 환경에서 |
| --- | --- | --- | --- |
| 무선 | LTE-V2X | 과기정통부·국토부 2023.12 | 가상 무선 채널(UDP)로 대신 — `radio/air.py` |
| 메시지 | SPaT, MAP, BSM (SAE J2735) | KS R 1600 | SAE J2735 2024 UPER — `common/j2735.py` |
| 메시지 봉투 | IEEE 1609.3 WSMP | | `common/wsmp.py` |
| 서명 | IEEE 1609.2 | CTI 4001, 항법학회지 2023 | 명시적 인증서, ECDSA P-256 — `common/sec1609.py` |
| 인증 체계 | SCMS 구조 | 자동차안전학회지 2021 | 루트 → 등록 CA·응용 CA — `ca/ca.py` |
| RSU 소프트웨어 | V2X-Hub (미국 교통부) | V2X-Hub README | V2X-Hub 8.1.0 (Docker) |
| 신호제어기 → RSU | NTCIP 1202 | | TSCBM — `tsc/tsc.py` |

## 전체 구조

```
                    CA (인증서 발급)
                 ┌────────┼────────┐
                 ▼        ▼        ▼
 SUMO ──위치──▶ OBU-01  OBU-02    RSU-01 = gateway.py + V2X-Hub + signer.py
 (교차로·차)      │ ▲      │ ▲         ▲ BSM(검증)      │ SPaT·MAP(서명)
      ▲          │ │      │ │         │                ▼
      └─정지/출발┘ └──────┴─┴═══ 가상 무선 (air.py) ═══┘
 SUMO 신호 ──▶ tsc.py ──▶ V2X-Hub SPaT 플러그인
```

- **차 → RSU**: OBU가 BSM을 서명해 방송 → RSU 게이트웨이가 검증 → V2X-Hub
- **RSU → 차**: V2X-Hub가 SPaT·MAP 생성 → RSU 서명기가 서명해 방송 → OBU가 검증 → 신호에 따라 정지·출발
- V2X-Hub는 RSU의 메시지 처리기이며 서명·검증 기능이 없어서, 앞에 검증 게이트웨이, 뒤에 서명기를 둔다.
- Docker 위에는 V2X-Hub만 있고, 나머지는 Ubuntu에서 일반 프로그램으로 실행된다.

## 폴더 구조

```
ca/ca.py                 CA 서버 (등록 인증서, 응용 인증서, 체인 배포). 키는 ca/data/ (Git 제외)
obu/obu.py               OBU (같은 코드로 OBU-01, OBU-02). BSM 서명·방송, SPaT·MAP 검증, 협력주행
rsu-gateway/gateway.py   RSU 수신: BSM 검증 → V2X-Hub (UDP 26789)
rsu-signer/signer.py     RSU 송신: V2X-Hub 출력(UDP 1516) → 서명 → 방송
tsc/tsc.py               가상 신호제어기: SUMO 신호 → TSCBM → V2X-Hub (UDP 6053)
tsc/make_map.py          SUMO 도로 → J2735 MAP 파일
radio/air.py             가상 무선 채널 (방송, 손실·지연 옵션)
common/                  공통 부품
  j2735.py               BSM·SPaT·MAP 생성·해석
  sec1609.py             IEEE 1609.2 인증서·서명·검증 (검증 4단계)
  identity.py            장치 시작 시 CA에서 인증서 받기
  wsmp.py, psid.py       메시지 봉투, 메시지 종류 번호
  intersection.py        MAP·SPaT 해석 (차로, 정지선 거리, 신호 색)
  radio.py, v2xlog.py    가상 무선 접속, 메시지별 JSON 로그
sumo/                    사거리 1개(판교 부근 가상 좌표), 차량 2대
scripts/run.sh           전체 실행
scripts/setup_ubuntu.sh  개발 환경 설치
scripts/build_j2735.sh   SAE J2735 ASN.1 → Python 변환기
v2xhub-config/           V2X-Hub 플러그인 설정 기록
docs/                    계획서, 단계별 기록
```

## 처음 설치 (한 번만)

1. 개발 환경: [docs/setup.md](docs/setup.md) (WSL2 + Ubuntu 24.04, Docker, SUMO, Python)
2. Python 라이브러리
   ```bash
   source ~/.venv/v2x/bin/activate
   pip install traci cryptography pycrate sumolib pyproj
   ```
3. **SAE J2735 파일**: SAE Mobilus(saemobilus.sae.org)에서 `J2735ASN_202409`를 받아(디스코드에 올려두었습니다) (무료, 계정 필요) 압축을 푼 뒤
   ```bash
   bash scripts/build_j2735.sh "<압축 푼 폴더>/V2X ASN.1 Module Collection 2024"
   ```
   → `common/j2735_gen.py` 생성. SAE 라이선스 때문에 원본과 생성 파일은 Git에 올리지 않는다.
4. V2X-Hub 8.1.0 설치: [docs/step1.md](docs/step1.md)
5. V2X-Hub 플러그인 설정과 MAP 파일: [v2xhub-config/plugins.md](v2xhub-config/plugins.md)

## 실행

```bash
# 1) Ubuntu를 열고 V2X-Hub 켜기
cd ~/V2X-Hub/configuration && docker compose up -d

# 2) VS Code로 저장소 열기 (선택)
cd ~/v2x-kr-testbed && code .

# 3) 전체 시뮬레이션 (SUMO 창이 뜸, Ctrl+C로 종료)
cd ~/v2x-kr-testbed
bash scripts/run.sh --coop
```

| 명령 | 용도 |
| --- | --- |
| `bash scripts/run.sh --coop` | 정상 실행: V2X로 받은 신호만 보고 협력주행 |
| `sumo-gui -c sumo/intersection.sumocfg` | SUMO 화면만 보기 (V2X 없음) |
| 브라우저 `https://127.0.0.1` | V2X-Hub 웹 관리 화면 (아이디 v2xadmin) |
| `cd ~/V2X-Hub/configuration && docker compose stop` | V2X-Hub 끄기 |

출력: `logs/*.out`(프로그램 화면), `logs/*.jsonl`(메시지마다 JSON 한 줄), `~/v2xhub_data/logs/json/`(V2X-Hub 기록)

## 보안 검증 (IEEE 1609.2)

받는 쪽은 아래 순서로 확인하고, 하나라도 실패하면 버리고 기록한다.

| 단계 | 검사 | 실패 이유 |
| --- | --- | --- |
| 1 | 서명 | UNSIGNED, BAD_SIGNATURE |
| 2 | 권한: 메시지 PSID가 인증서에 있는가 (OBU=BSM, RSU=SPaT·MAP) | NO_PERMISSION |
| 3 | 유효기간 | CERT_EXPIRED |
| 4 | 발급 체인: 신뢰하는 루트까지 이어지는가 | UNKNOWN_ISSUER |

구현 설명: [docs/step4-6.md](docs/step4-6.md)

## 단계별 기록

| 단계 | 내용 | 문서 |
| --- | --- | --- |
| 0 | 개발 환경 | [docs/setup.md](docs/setup.md) |
| 1 | V2X-Hub BSM 수신 | [docs/step1.md](docs/step1.md) |
| 2 | OBU 2대 BSM 전송 | [docs/step2.md](docs/step2.md) |
| 3, 3-1 | RSU SPaT·MAP 방송, 협력주행 | [docs/step3.md](docs/step3.md) |
| 4~6 | CA, 서명·검증 | [docs/step4-6.md](docs/step4-6.md) |

## 단순화한 점과 2차 과제

- 무선은 가상(UDP), 인증서는 명시적·1장 고정, CA는 3개 기관으로 단순화, CA 통신은 HTTP
- RSU·OBU·CA는 일반 프로그램으로 실행 (V2X-Hub만 Docker)
- 2차 과제(추가 보안): 재전송 검사, 시각 교차 검사, SPaT 개연성 검사, 위치 대조, 속도 제한, CRL, 인증서 자동 갱신·익명 교체, HSM, HTTPS, Docker 네트워크 분리 + iptables

## 사용한 오픈소스

- [V2X-Hub](https://github.com/usdot-fhwa-OPS/V2X-Hub) (Apache 2.0) — 저장소에 포함하지 않고 별도 설치
- [Eclipse SUMO](https://eclipse.dev/sumo/)
- [pycrate](https://github.com/pycrate-org/pycrate) — ASN.1 컴파일·인코딩 (IEEE 1609.2 ASN.1 포함)
- [cryptography](https://cryptography.io/) — ECDSA P-256
- SAE J2735 ASN.1 (J2735ASN_202409) — SAE 라이선스, 저장소에 포함하지 않음
