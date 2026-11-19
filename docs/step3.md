# 3단계 + 3-1단계: RSU의 SPaT·MAP 방송과 협력주행

## 결과: 통과 (2026-11-19, 실제 V2X-Hub 8.1.0)
- OBU-02가 V2X-Hub가 만든 MAP을 받아 자기 차로(3)와 정지선 거리를 계산
- SUMO 신호등 준수를 끈 상태에서, V2X로 받은 SPaT만 보고 빨간불에 정지선 2.1 m 앞 정지(t=20 s), 초록불에 출발(t=46 s)
- 받은 SPaT 신호 변화 시각이 SUMO 신호 변화(45.1 s)와 일치

## 구조
    SUMO 신호 -> tsc/tsc.py (TSCBM, UDP 6053) -> V2X-Hub SPAT 플러그인 -> J2735 SPaT
    tsc/make_map.py -> MAP 파일 -> V2X-Hub MAP 플러그인 -> J2735 MAP
    V2X-Hub ImmediateForward (RSU 4.1 형식, UDP 1516) -> rsu-signer/signer.py -> WSMP -> radio/air.py
    radio/air.py -> obu/obu.py (SPaT·MAP 해석, 협력주행)
    obu/obu.py (BSM) -> radio/air.py -> rsu-gateway/gateway.py -> V2X-Hub MessageReceiver (UDP 26789)

## 실제 표준과 맞춘 부분
- 메시지: SAE J2735 2024 (BSM, SPaT, MAP) UPER
- 메시지 봉투: IEEE 1609.3 WSMP 헤더 (PSID p-encoding)
- 신호제어기 -> RSU: NTCIP 1202 TSCBM (V2X-Hub 표본 바이너리와 같은 241바이트 구조)
- RSU 소프트웨어 출력: RSU 4.1 형식

## 안전 장치
- MAP을 받기 전에는 V2X 주행으로 넘어가지 않고 SUMO 신호를 지킴
- SPaT를 1초 넘게 못 받으면 신호를 UNKNOWN으로 보고 감속·정지

## 실행
    bash scripts/run.sh --coop        # V2X-Hub 플러그인 설정: v2xhub-config/plugins.md

## 겪은 문제
| 증상 | 원인 | 해결 |
| --- | --- | --- |
| make_map.py PermissionError | ~/v2xhub_data/download가 Docker(root) 소유 | sudo로 MAP 폴더 생성 후 chown |
| OBU가 MAP 0개 | MAP 플러그인이 기본 파일 경로를 읽은 채 실행 | 설정 저장 후 Disable → 다시 켜기 |
| logs/*.out이 실행 중 비어 있음 | Python 출력 버퍼링 | run.sh에서 python3 -u |
