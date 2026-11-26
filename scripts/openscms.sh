#!/usr/bin/env bash
# OpenSCMS(minikube) 켜기/끄기와 주소 연결
# 사용법: bash scripts/openscms.sh start | stop | status
#   start : minikube를 켜고(이미 켜져 있으면 그대로), ECA·RA·ACA를 127.0.0.1:8091~8093에 연결한다.
#           연결은 뒤에서 계속 돌아가므로 창을 켜 둘 필요가 없다.
#   stop  : 주소 연결만 끊는다 (minikube까지 끄려면: minikube stop)
#   status: 연결 상태와 각 기관 응답 확인
cd "$(dirname "$0")/.."
mkdir -p logs
PIDS=logs/openscms-port-forward.pids
SERVICES="eca-external-service:8091 ra-external-service:8092 aca-external-service:8093"

stop_pf() {
  if [ -f "$PIDS" ]; then
    kill $(cat "$PIDS") 2>/dev/null || true
    rm -f "$PIDS"
  fi
  pkill -f "kubectl port-forward svc/(eca|ra|aca)-external-service" 2>/dev/null || true
}

check() {
  for s in "ECA:8091" "RA:8092" "ACA:8093"; do
    code=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${s#*:}/healthcheck" || true)
    echo "  ${s%%:*} (127.0.0.1:${s#*:}) -> ${code:-응답 없음}"
  done
}

case "$1" in
  start)
    if ! minikube status 2>/dev/null | grep -q "host: Running"; then
      echo "minikube 켜는 중..."
      minikube start --memory=8g --cpus=4
    fi
    echo "OpenSCMS 기관이 모두 뜰 때까지 기다리는 중..."
    kubectl wait --for=condition=Ready pod --all --timeout=300s >/dev/null
    stop_pf
    for s in $SERVICES; do
      nohup kubectl port-forward "svc/${s%%:*}" "${s#*:}:5000" > "logs/pf-${s%%-*}.log" 2>&1 &
      echo $! >> "$PIDS"
    done
    sleep 2
    check
    ;;
  stop)
    stop_pf; echo "주소 연결을 끊었습니다."
    ;;
  status)
    kubectl get pods 2>/dev/null | head -20
    check
    ;;
  *)
    echo "사용법: bash scripts/openscms.sh start | stop | status"; exit 1
    ;;
esac
