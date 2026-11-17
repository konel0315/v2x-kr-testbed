# 1단계: V2X-Hub 실행과 BSM 수신 확인

## 결과: 통과 (2026-11-17)

샘플 UPER BSM 63개를 UDP 26789로 보냈고, JSON 로그에 63개 모두 디코딩되어 기록됨.

## 환경

- V2X-Hub 8.1.0 (`git clone --branch 8.1.0`, 저장소 밖 `~/V2X-Hub`에 설치)
- `configuration/initialization.sh` 실행. 데이터 경로는 `/home/<user>/v2xhub_data` (`/tmp`는 재시작 시 지워질 수 있어 변경)
- 컨테이너: db(mysql 8.0.40), php(웹 UI), v2xhub. 모두 healthy

## 켠 플러그인

| 플러그인 | 설정 |
| --- | --- |
| CommandPlugin | 기본 (웹 UI 연결, 19760) |
| MessageReceiver | 기본 (Port 26789, RouteJ2735 false) |
| JSONMessageLoggerPlugin | 기본 (LogDir /var/log/tmx/json → 호스트 ~/v2xhub_data/logs/json) |

## 시험 방법

```bash
python3 ~/V2X-Hub/src/v2i-hub/MessageReceiverPlugin/scripts/sendBsms.py   # 5초 후 Ctrl+C
wc -l ~/v2xhub_data/logs/json/rsu_1234_j2735Rx_*.log
tail -n 1 ~/v2xhub_data/logs/json/rsu_1234_j2735Rx_*.log
```

## 로그 예시 (coreData 부분)

```
"messageId":"20", "BasicSafetyMessage":{"coreData":{"msgCnt":"46","id":"54310000",
"lat":"389561210","long":"-771500090","speed":"3","heading":"18264", ...}}
```

단위: lat/long 1e-7도, speed 0.02 m/s, heading 0.0125도.
샘플 BSM은 V2X-Hub에 포함된 것으로, 미국 버지니아 부근 좌표의 긴급차량 BSM이다.

## 겪은 문제와 해결

| 증상 | 원인 | 해결 |
| --- | --- | --- |
| 웹 UI 비밀번호 `INVALID PASSWORD` | 8~12자, 대문자·소문자·숫자·기호 각 1개 필요 | 규칙에 맞게 다시 실행 |
| 브라우저 "연결이 비공개로 설정되어 있지 않습니다" | V2X-Hub 자체 서명 인증서 | 고급 → 계속 (2차 A-4에서 신뢰 인증서로 교체 예정) |
| 로그인 후 `Connecting to wss://127.0.0.1:19760` 반복 | 19760 웹소켓의 인증서를 브라우저가 따로 허용해야 함 | https://127.0.0.1:19760 을 열어 경고를 허용한 뒤, UI를 https://127.0.0.1 로 다시 접속 |
| 플러그인 목록에 CommandPlugin만 보임 | 필터가 Enabled로 선택됨 | Disabled 필터에서 플러그인 이름 왼쪽 네모를 눌러 켬 |
| Claude 앱 내장 브라우저로 UI 열기 실패 (`ERR_CERT_AUTHORITY_INVALID`) | 내장 브라우저는 자체 서명 인증서를 허용하지 않음 | 신뢰 인증서 적용 전까지 일반 브라우저 사용 |

## 확인된 사실 (이후 단계용)

- MessageReceiver는 받은 바이트의 첫 바이트가 `0x00`이면 UPER로 처리 → J2735 MessageFrame을 그대로 보내면 됨
- MessageReceiver의 `FullSPDUMode`는 1609.2 봉투를 풀기만 하고 서명 검증은 하지 않음 → 앞단 검증 게이트웨이 필요
- SPaT 플러그인은 UDP 6053으로 TSCBM 바이너리를 받아 SPaT 생성 (SNMP 불필요)
- V2X-Hub PSID: BSM `0x20`, SPaT `0x8002`, MAP `0xE0000017`
