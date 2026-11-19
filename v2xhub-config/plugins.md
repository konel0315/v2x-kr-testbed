# V2X-Hub 8.1.0 플러그인 설정 (웹 UI https://127.0.0.1 → Plugins)

설정을 바꾼 뒤 플러그인을 켠다. 이미 켜져 있으면 Disable → F5 → 다시 켜서 새 설정을 읽게 한다.

| 플러그인 | 키 | 값 |
| --- | --- | --- |
| MessageReceiver | (기본값) | Port 26789 |
| JSONMessageLoggerPlugin | (기본값) | 로그: ~/v2xhub_data/logs/json |
| SPAT | SignalGroupMapping | {"SignalGroups":[{"SignalGroupId":2,"Phase":2,"Type":"vehicle"},{"SignalGroupId":4,"Phase":4,"Type":"vehicle"},{"SignalGroupId":6,"Phase":6,"Type":"vehicle"},{"SignalGroupId":8,"Phase":8,"Type":"vehicle"}]} |
| SPAT | (나머지 기본값) | SPAT_Mode TSCBM, Local_UDP_Port 6053, Intersection_Id 1 |
| MAP | MAP_Files | {"MapFiles":[{"Action":0,"FilePath":"/var/www/download/MAP/pangyo_map.txt"}]} |
| ImmediateForward | ImmediateForwardConfigurations | [{"name":"Virtual Radio","rsuSpec":"RSU4.1","address":"host.docker.internal","port":1516,"txMode":"CONT","signMessages":false,"messages":[{"tmxType":"SPAT-P","sendType":"SPAT","psid":"0x8002","channel":183},{"tmxType":"MAP-P","sendType":"MAP","psid":"0xE0000017","channel":183}]}] |

## MAP 파일 준비 (호스트)
    sudo mkdir -p ~/v2xhub_data/download/MAP
    sudo chown $USER ~/v2xhub_data/download/MAP
    python3 tsc/make_map.py --out ~/v2xhub_data/download/MAP/pangyo_map.txt

## 주의
- MAP 플러그인을 먼저 켜고 나중에 경로를 바꾸면 기본 파일(MAP_9709_UPER.txt)을 계속 찾는다 → Disable 후 다시 켜기
- ImmediateForward 기본 설정은 MAP PSID가 0x8002라서 0xE0000017로 바꿈
- SPaT 플러그인은 TSC 메시지 간격이 300 ms(CTI 4501)를 넘으면 경고를 남긴다
