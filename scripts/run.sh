#!/usr/bin/env bash
# 전체 실행: SCMS 인증서 준비(OpenSCMS), 가상 무선, RSU(검증 게이트웨이·서명기), 교통센터(V2N),
#           SUMO, 신호제어기, OBU 2대, 보행자 단말(V2P)
# 사용법: bash scripts/run.sh [옵션]
#   --coop            V2X로 받은 정보로 협력주행 (신호, 보행자, 공사 구간)
#   --no-ped          보행자가 길을 건너지 않음
#   --no-v2n          교통센터를 켜지 않음 (V2N 없이)
# V2X-Hub(docker compose)는 미리 켜 두고, 플러그인은 v2xhub-config/plugins.md 대로 설정한다.
# OpenSCMS는 bash scripts/openscms.sh start 로 켜 둔다 (127.0.0.1:8091~8093).
# 각 프로그램 출력은 logs/*.out, 메시지별 기록은 logs/*.jsonl. Ctrl+C로 모두 종료.
cd "$(dirname "$0")/.."
COOP=""; PED=""; V2N=1
for a in "$@"; do
  case "$a" in
    --coop) COOP="--coop";;
    --no-ped) PED="--no-cross";;
    --no-v2n) V2N=0;;
  esac
done
OBU_OPT="$COOP"; [ "$V2N" = 0 ] && OBU_OPT="$OBU_OPT --no-v2n"
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
[ "$V2N" = 1 ] && start center python3 -u center/center.py
sleep 1.5
start sumo     sumo-gui -c sumo/intersection.sumocfg --remote-port 8813 --num-clients 4 --start --delay 100
sleep 2
start tsc      python3 -u tsc/tsc.py --order 3
start ped      python3 -u ped/ped.py --order 4 $PED
start obu1     python3 -u obu/obu.py --vehicle obu1 --order 1 $OBU_OPT
start obu2     python3 -u obu/obu.py --vehicle obu2 --order 2 $OBU_OPT
echo "실행 중 (협력주행 ${COOP:-끔}, V2N $([ "$V2N" = 1 ] && echo 켬 || echo 끔)). SUMO 창에서 확인하세요."
echo "아래는 OBU·보행자·교통센터 화면입니다. 각 파일: logs/obu1.out obu2.out ped.out center.out"
tail -f logs/obu1.out logs/obu2.out logs/ped.out $([ "$V2N" = 1 ] && echo logs/center.out)
