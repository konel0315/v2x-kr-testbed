#!/usr/bin/env bash
# 전체 실행: SCMS 인증서 준비(OpenSCMS), 가상 무선, RSU(검증 게이트웨이·서명기), SUMO, 신호제어기, OBU 2대
# 사용법: bash scripts/run.sh [옵션]
#   --coop            V2X 신호로 협력주행 (3-1단계)
# V2X-Hub(docker compose)는 미리 켜 두고, 플러그인은 v2xhub-config/plugins.md 대로 설정한다.
# OpenSCMS는 bash scripts/openscms.sh start 로 켜 둔다 (127.0.0.1:8091~8093).
# 각 프로그램 출력은 logs/*.out, 메시지별 기록은 logs/*.jsonl. Ctrl+C로 모두 종료.
cd "$(dirname "$0")/.."
COOP=""
for a in "$@"; do
  case "$a" in
    --coop) COOP="--coop";;
  esac
done
mkdir -p logs
PIDS=()
start() { local name=$1; shift; "$@" > "logs/$name.out" 2>&1 & PIDS+=($!); }
cleanup() { echo; echo "종료 중..."; kill "${PIDS[@]}" 2>/dev/null; wait 2>/dev/null; }
trap cleanup EXIT INT TERM

# 1) OBU·RSU 인증서 준비 (IEEE 1609.2.1: 등록 → 등록인증서 → 응용인증서). 이미 있으면 재사용
if ! curl -s -o /dev/null "http://127.0.0.1:8092/healthcheck"; then
  echo "OpenSCMS(RA 127.0.0.1:8092)에 연결할 수 없습니다. 먼저: bash scripts/openscms.sh start"
  exit 1
fi
python3 -u scripts/provision.py || exit 1

start air      python3 -u radio/air.py
start gateway  python3 -u rsu-gateway/gateway.py
start signer   python3 -u rsu-signer/signer.py
sleep 1.5
start sumo     sumo-gui -c sumo/intersection.sumocfg --remote-port 8813 --num-clients 3 --start --delay 100
sleep 2
start tsc      python3 -u tsc/tsc.py --order 3
start obu1     python3 -u obu/obu.py --vehicle obu1 --order 1 $COOP
start obu2     python3 -u obu/obu.py --vehicle obu2 --order 2 $COOP
echo "실행 중 (협력주행 ${COOP:-끔}). SUMO 창에서 확인하세요. 아래는 OBU 화면입니다."
tail -f logs/obu1.out logs/obu2.out
