#!/usr/bin/env bash
# V2X 가상환경: Ubuntu 24.04 (WSL2) 개발 환경 설치
# 사용법: bash scripts/setup_ubuntu.sh
# 자세한 설명: docs/setup.md
set -e

echo "== 1. systemd 확인"
if [ "$(ps -p 1 -o comm=)" != "systemd" ]; then
  echo "systemd가 꺼져 있습니다. 아래를 실행한 뒤 PowerShell에서 'wsl --shutdown' 후 다시 실행하세요."
  echo '  echo -e "[boot]\nsystemd=true" | sudo tee -a /etc/wsl.conf'
  exit 1
fi

echo "== 2. Docker Engine"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
fi
sudo usermod -aG docker "$USER"

echo "== 3. SUMO, git, GitHub CLI, Python venv"
if ! grep -rq "sumo/stable" /etc/apt/sources.list.d/ 2>/dev/null; then
  sudo add-apt-repository -y ppa:sumo/stable
fi
sudo apt update
# PPA 서버가 503을 내면 몇 번 다시 시도
for i in 1 2 3; do
  if sudo apt install -y sumo sumo-tools sumo-doc python3-venv git gh; then
    break
  fi
  echo "설치 실패, 30초 뒤 다시 시도 ($i/3)"
  sleep 30
done

echo "== 4. Python 가상환경"
VENV="$HOME/.venv/v2x"
if [ ! -d "$VENV" ]; then
  python3 -m venv "$VENV"
fi
if ! grep -q "$VENV/bin/activate" "$HOME/.bashrc"; then
  echo "source $VENV/bin/activate" >> "$HOME/.bashrc"
fi
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install traci cryptography asn1tools

echo "== 5. 확인"
sumo --version | head -1
"$VENV/bin/python" -c "import traci, cryptography, asn1tools; print('Python 라이브러리 OK')"

echo
echo "완료. docker 권한을 적용하려면 Ubuntu를 닫았다 다시 연 뒤 'docker run --rm hello-world'로 확인하세요."
