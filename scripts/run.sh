#!/usr/bin/env bash
# 전체 실행: 가상 무선, RSU(게이트웨이·송신부), SUMO, 신호제어기, OBU 2대
# 사용법: bash scripts/run.sh            (V2X 정보 표시만)
#         bash scripts/run.sh --coop     (3-1단계: V2X 신호로 협력주행)
#         bash scripts/run.sh --mock     (V2X-Hub 없이 시험: tests/mock_v2xhub.py 사용)
# V2X-Hub(docker compose)는 미리 켜 두고, SPaT·MAP·ImmediateForward 플러그인을 설정해 둔다.
# 각 프로그램 출력은 logs/*.out, 메시지별 기록은 logs/*.jsonl 에 남는다. Ctrl+C로 모두 종료.
cd "$(dirname "$0")/.."
COOP=""; MOCK=0
for a in "$@"; do
  case "$a" in --coop) COOP="--coop";; --mock) MOCK=1;; esac
done
mkdir -p logs
PIDS=()
start() { local name=$1; shift; "$@" > "logs/$name.out" 2>&1 & PIDS+=($!); }
cleanup() { echo; echo "종료 중..."; kill "${PIDS[@]}" 2>/dev/null; wait 2>/dev/null; }
trap cleanup EXIT INT TERM

start air      python3 radio/air.py
start gateway  python3 rsu-gateway/gateway.py
start signer   python3 rsu-signer/signer.py
if [ $MOCK = 1 ]; then
  if ss -uln | grep -qE ':(6053|26789)\b'; then
    echo "V2X-Hub가 켜져 있어 흉내 프로그램이 같은 포트(6053, 26789)를 쓸 수 없습니다."
    echo "먼저 V2X-Hub를 끄세요:  cd ~/V2X-Hub/configuration && docker compose stop"
    exit 1
  fi
  python3 tsc/make_map.py --out logs/map_mock.txt > /dev/null || { echo "MAP 생성 실패 (pip install sumolib pyproj 했는지 확인)"; exit 1; }
  start mock   python3 tests/mock_v2xhub.py --map logs/map_mock.txt
fi
sleep 1
start sumo     sumo-gui -c sumo/intersection.sumocfg --remote-port 8813 --num-clients 3 --start --delay 100
sleep 2
start tsc      python3 tsc/tsc.py --order 3
start obu1     python3 obu/obu.py --vehicle obu1 --order 1 $COOP
start obu2     python3 obu/obu.py --vehicle obu2 --order 2 $COOP
echo "실행 중 (협력주행 ${COOP:-끔}). SUMO 창에서 확인하세요. 아래는 OBU 화면입니다."
tail -f logs/obu1.out logs/obu2.out logs/tsc.out
