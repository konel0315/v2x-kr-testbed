# 개발 환경 설치 기록

이 문서대로 하면 팀원 누구나 같은 환경을 만들 수 있다. Ubuntu 쪽 설치는 `scripts/setup_ubuntu.sh` 하나로 한 번에 할 수 있다.

## 확인된 환경

| 항목 | 버전 |
| --- | --- |
| 호스트 | Windows + WSL2 (WSL 3.0.5) |
| 리눅스 | Ubuntu 24.04 LTS (WSL 안) |
| Docker | Docker Engine (WSL 안에 직접 설치), Docker Compose v5.7.2 |
| 교통 시뮬레이터 | Eclipse SUMO 1.28.0 (ppa:sumo/stable) |
| Python | 3.12 (가상환경 `~/.venv/v2x`) |
| Python 라이브러리 | traci, cryptography, asn1tools |

권장 사양: 호스트 RAM 16 GB 이상, WSL에 8 GB 할당.

## 1. WSL2와 Ubuntu (Windows)

PowerShell을 관리자 권한으로 열고 실행한다.

```powershell
wsl --install -d Ubuntu-24.04
```

설치가 끝나면 Ubuntu 사용자 이름과 비밀번호를 정한다.

WSL 메모리 한도를 정한다. Ubuntu 안에서 Windows 사용자 폴더에 파일을 만들면 된다 (`<이름>`은 Windows 사용자 이름).

```bash
printf "[wsl2]\nmemory=8GB\n" > /mnt/c/Users/<이름>/.wslconfig
```

systemd가 켜져 있는지 확인한다. Docker 서비스가 자동으로 실행되려면 필요하다.

```bash
ps -p 1 -o comm=      # systemd 가 나와야 함
```

`systemd`가 아니면 다음을 실행한다.

```bash
echo -e "[boot]\nsystemd=true" | sudo tee -a /etc/wsl.conf
```

설정을 적용하려면 Ubuntu에서 `exit`로 나간 뒤 **PowerShell에서** `wsl --shutdown`을 실행하고 Ubuntu를 다시 연다.

확인: `free -h`의 Mem total이 약 7.8Gi.

## 2. Ubuntu 안의 설치

```bash
bash scripts/setup_ubuntu.sh
```

스크립트가 하는 일은 아래와 같다. 수동으로 해도 된다.

```bash
# Docker Engine
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER          # 적용하려면 Ubuntu 재접속

# SUMO, git, GitHub CLI, Python venv
sudo add-apt-repository -y ppa:sumo/stable
sudo apt update
sudo apt install -y sumo sumo-tools sumo-doc python3-venv git gh

# Python 가상환경
python3 -m venv ~/.venv/v2x
echo 'source ~/.venv/v2x/bin/activate' >> ~/.bashrc
source ~/.venv/v2x/bin/activate
pip install traci cryptography asn1tools
```

## 3. 확인

```bash
docker run --rm hello-world            # "Hello from Docker!"
docker compose version
sumo --version | head -1               # Eclipse SUMO sumo Version 1.28.0
sumo-gui                               # Windows 화면에 창이 뜨면 정상 (WSLg)
python3 -c "import traci, cryptography, asn1tools; print('OK')"
```

## 설치 중 겪은 문제와 해결

| 증상 | 원인 | 해결 |
| --- | --- | --- |
| Ubuntu 안에서 `wsl --shutdown` → `command not found` | `wsl`은 Windows 명령 | PowerShell에서 실행 |
| Docker 설치 스크립트가 "WSL DETECTED: We recommend using Docker Desktop" 출력 후 멈춤 | 안내 메시지와 20초 대기 | Ctrl+C 누르지 않고 기다리면 계속 진행됨 |
| SUMO 설치 중 `503 Service Unavailable` | Launchpad(PPA) 서버 일시 장애 | 같은 `apt install` 명령을 다시 실행 (받아 둔 파일은 재사용됨). 계속 실패하면 PPA를 제거하고 Ubuntu 기본 저장소의 SUMO 사용 |

## 설계상 선택과 이유

- **Docker Desktop 대신 WSL 안에 Docker Engine 직접 설치**: 2차 보안 단계에서 호스트 iptables `DOCKER-USER` 체인으로 접근 통제와 속도 제한을 실습해야 한다. Docker Desktop은 데몬이 별도 VM에 있어 이 실습이 어렵다.
- **rootless 모드 사용 안 함**: rootless Docker는 호스트 iptables를 다루지 못해 위 실습이 불가능하다.

## 알려진 위험

- `docker` 그룹에 속한 사용자는 Docker 데몬을 통해 사실상 root 권한을 가진다 (설치 스크립트 경고 참고: https://docs.docker.com/go/attack-surface/). 개인 실습 PC이므로 허용했다. 공용 서버에서는 계정 관리에 주의한다.
- `gh auth login`은 GitHub 로그인 토큰을 `~/.config/gh/hosts.yml`에 평문으로 저장한다. 개인 PC이므로 허용했다. WSL에는 브라우저가 없어 자동으로 열리지 않으므로 https://github.com/login/device 를 Windows 브라우저에서 직접 열어 코드를 입력한다.
