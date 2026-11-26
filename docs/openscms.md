# 8단계: 인증서 발급을 OpenSCMS(IEEE 1609.2.1)로 교체

4~6단계에서는 직접 만든 작은 CA(`ca/ca.py`)가 인증서를 발급했다. 이 단계에서 그것을 오픈소스 SCMS인
**OpenSCMS**(LG전자, Apache 2.0)로 바꾸고, 장치(OBU·RSU)가 **IEEE 1609.2.1 절차 그대로** 인증서를 받게 했다.

## 무엇이 바뀌었나

| | 4~6단계 (자체 CA) | 지금 (OpenSCMS) |
| --- | --- | --- |
| 인증 기관 | 프로그램 1개가 루트·등록 CA·응용 CA 역할 | ECA, RA, ACA, LA×2, CAM이 각각 따로 동작 (minikube) |
| 표준 판 | IEEE 1609.2 (2016 ASN.1) | IEEE 1609.2-2022, 1609.2.1-2022 |
| 요청 형식 | JSON + 서명 | 1609.2.1 SPDU (COER) |
| 등록인증서 | 명시적 | **암묵적(implicit)** — 비밀키를 장치가 직접 복원 |
| 응용인증서 요청 | 평문 | **RA 공개키로 암호화** (ECIES + AES-CCM), 등록인증서로 서명 |
| 응용인증서 | 장치 이름이 들어감 | **익명** (무작위 번호), 발급은 ACA |
| 권한(PSID) | CA가 장치 이름으로 결정 | 장치가 요청, **RA가 장치 종류(OBU/RSU)별 정책으로 허용 여부 판단**, ACA가 인증서에 기록 |
| 신뢰 목록 | CA가 준 체인 | 장치에 설치된 루트 + RA에서 받은 ICA·ACA (루트로 서명 확인 후 신뢰) |

V2X 메시지(BSM, SPaT, MAP)의 서명·검증 4단계는 그대로다.

## 발급 순서 (장치 1대)

```
장치                                    OpenSCMS
 │ 0. 등록: 대표키(canonical key) 공개키 ──▶ RA(DCM)  POST /dcms/device/na        (공장 출고 단계)
 │ 1. EeEcaCertRequestSpdu ────────────────▶ ECA      POST /v3/enrollment-certificate
 │    (대표키로 자체 서명, 새 키 k의 공개키)
 │ ◀──────────────── EcaEeCertResponseSpdu (ECA 서명, 암묵적 등록인증서 + 복원값 r)
 │    등록 비밀키 = e·k + r  (e = 인증서 해시)  → d·G 가 인증서에서 복원한 공개키와 같은지 확인
 │ 2. EeRaCertRequestSpdu ─────────────────▶ RA       POST /v3/authorization-certificate
 │    (응용 공개키 + 요청 PSID, 등록인증서로 서명 → RA 암호화 공개키로 암호화)
 │                                           RA: 등록 여부·차단 여부·PSID 정책 확인 → ACA에 발급 요청
 │ ◀──────────────── RaEeCertAckSpdu (RA 서명, requestHash, 다운로드 가능 시각)
 │ 3. GET /v3/authorization-certificate ──▶ RA
 │    헤더 Ieee-1609.2.1-Authorization = EeRaDownloadRequestSpdu (서명 + 암호화)
 │ ◀──────────────── zip: AcaEeCertResponse (응용인증서)
```

코드: `common/scms_client.py` (절차), `common/scms_crypto.py` (ECIES, AES-CCM, 암묵적 인증서 계산), `common/identity.py` (장치별 설정과 신뢰 목록), `scripts/provision.py` (3대 한 번에)

## OpenSCMS에 한 수정 (`openscms-patch/`)

원래 OpenSCMS는 응용인증서의 `appPermissions`(PSID 권한)를 **비워서** 발급한다. 그러면 받는 쪽이 "이 인증서로 이 메시지를 보내도 되는가"(검증 2단계)를 확인할 수 없다. 표준(1609.2.1 EeRaCertRequest)은 장치가 `appPermissions`를 요청하고 그 권한으로 발급하도록 되어 있으므로, 그렇게 고쳤다.

| 파일 | 수정 |
| --- | --- |
| `oscms-codecs-bridge/src/ee_ra_cert_request.c` | 요청의 `tbsCert.appPermissions`에서 PSID를 꺼냄 |
| `oscms-codecs-bridge/src/certificate_util.c`, `aca_ee_cert_response.c` | ACA가 그 PSID를 응용인증서 `appPermissions`에 넣음 |
| `oscms_bridge/src/bridge/*.rs`, `scmscommon/.../caterpillar.rs` | PSID를 RA → ACA로 전달 |
| `ra/src/ra_endpoint/authorization_cert.rs` | RA가 장치 종류별 허용 PSID만 받음. 아니면 `400-30 disallowed appPermissions` |
| `aca/src/core_logic/build_certificates.rs` | NonButterfly 응용인증서 유효기간을 "지금부터 1년"으로 (원래는 2004년부터) |
| `deployment/values.yaml` | PSID 정책 `RA_PSID_POLICY_OBU="0x20"`, `RA_PSID_POLICY_RSU="0x8002,0xE0000017"`. 모든 장치가 한 IP(port-forward)로 접속하므로 요청 횟수 제한을 늘리고, 요청 생성 시각 허용 오차를 30초로 |

적용·되돌리기:

```bash
bash ~/v2x-kr-testbed/openscms-patch/apply.sh     # 적용
bash ~/v2x-kr-testbed/openscms-patch/revert.sh    # 되돌리기
cd ~/openscms/OpenSCMS && skaffold run            # 어느 쪽이든 다시 빌드해야 반영됨
```

## 시험한 것

OpenSCMS의 C 코덱(`oscms-codecs-bridge`)을 그대로 빌드해 ECA·RA·ACA 처리 함수에 우리 요청을 넣어 확인했다.

- OpenSCMS 시험 데이터(`EeEcaCertRequestSpdu.dat`, `EeRaCertRequestSpdu.dat`, `EeRaDownloadRequestSpdu.dat`)를 우리 코드로 복호화·서명 확인 → 성공 (ECIES, 암묵적 인증서, 서명 해시가 OpenSCMS와 같음)
- 우리 요청 → OpenSCMS 코덱: 등록인증서 발급, 응용인증서 요청 복호화·서명 확인, 다운로드 요청 확인, 응용인증서 발급 → 모두 성공
- 수정본에서 응용인증서에 PSID가 들어감: OBU `[0x20]`, RSU `[0x8002, 0xE0000017]`
- 받은 인증서로 V2X 메시지 검증: 정상 BSM·SPaT 통과, OBU 인증서로 만든 SPaT → `NO_PERMISSION`, 변조 → `BAD_SIGNATURE`, 기간 밖 → `CERT_EXPIRED`, 서명 없음 → `UNSIGNED`
- Rust 쪽 수정은 `cargo check`로 컴파일 확인

## 단순화한 점

- **NonButterfly**: 응용인증서를 장치당 1장 받는다. 실제 OBU는 버터플라이 키 확장으로 기간별 여러 장(익명 인증서 묶음)을 받아 주기적으로 바꿔 쓴다. OpenSCMS는 버터플라이도 지원하므로 2차 과제에서 확장할 수 있다.
- **전송 구간**: HTTP. 1609.2.1이 요구하는 TLS와 OAuth 토큰은 생략했다 (요청 자체는 서명·암호화됨).
- **루트 설치**: 루트 인증서는 출고 때 장치에 넣는다고 보고, OpenSCMS 폴더의 `certs/rootca/rootcaCertificate.coer`를 처음 한 번 `ee-data/trust/root.cert`로 복사한다.
- **CTL/CRL**: 신뢰 목록(CTL)과 폐기 목록(CRL) 다운로드는 하지 않는다 (2차 과제).
- 메시지에는 서명자 인증서를 통째로 넣는다 (실제로는 대부분 HashedId8만 넣고 가끔 인증서를 넣음).

## 파일 위치

| 위치 | 내용 |
| --- | --- |
| `~/openscms/OpenSCMS/` | OpenSCMS (저장소에 넣지 않음) |
| `~/openscms/OpenSCMS/certs/` | 기관 인증서·키 (설치 때 생성, 비밀키 포함 — 올리지 않음) |
| `ee-data/<장치>/` | 장치 키(`*.key`)와 인증서(`*.cert`), 등록 정보 (Git 제외) |
| `ee-data/trust/root.cert` | 장치에 설치된 루트 인증서 |
| `common/ieee1609_gen.py` | IEEE 1609.2/1609.2.1 ASN.1 변환기 (`scripts/build_ieee1609.sh`로 생성, Git 제외) |

## 문제 해결

| 증상 | 원인 | 해결 |
| --- | --- | --- |
| `kubectl get pods`에 `CrashLoopBackOff` | 메모리 부족 또는 DB가 아직 안 뜸 | 2~3분 기다린 뒤 다시 확인. 계속되면 `.wslconfig` 메모리 늘리고 `wsl --shutdown`(PowerShell) |
| `skaffold run`이 오래 멈춘 것 같음 | Rust 빌드 중 | 처음에는 20~40분 정상 |
| `openscms.sh start`에서 `응답 없음` | minikube가 아직 시작 중 | 1분 뒤 `bash scripts/openscms.sh start` 다시 |
| `연결 실패 ... port-forward` | 주소 연결이 끊김 (WSL 재시작 등) | `bash scripts/openscms.sh start` |
| `HTTP 400 400-21` | OpenSCMS를 새로 설치해 예전 등록이 없음 | `python3 scripts/provision.py --reset` |
| `HTTP 400 400-30` | 장치 종류에 허용되지 않은 PSID 요청 | `common/identity.py`의 `DEVICES`와 `values.yaml` 정책 확인 |
| `응용인증서에 PSID ... 권한이 없습니다` | 수정본이 빌드되지 않음 | `apply.sh` 후 `skaffold run` |
| `루트 인증서가 없습니다` | OpenSCMS 폴더 위치가 다름 | `export OPENSCMS_DIR=OpenSCMS폴더` 후 다시 실행 |
| `ASN 파일이 부족합니다` | OpenSCMS를 서브모듈 없이 받음 | `cd ~/openscms/OpenSCMS && git submodule update --init --recursive` |
