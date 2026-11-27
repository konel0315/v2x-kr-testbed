# V2X 가상환경 (한국 C-ITS 기준) — RSU 1, OBU 2, 보행자 1, 교통센터 1, SCMS 1

국내 C-ITS 표준을 전제로 V2X 통신의 기본 보안(IEEE 1609.2 서명·검증)을 오픈소스 가상환경에서 구현한다.
모든 메시지는 서명되고, 받는 쪽은 검증을 통과한 메시지만 쓴다.
인증서는 오픈소스 SCMS인 **OpenSCMS**(IEEE 1609.2.1)가 실제 절차(등록 → 등록인증서 → 응용인증서 → 다운로드)대로 발급한다.
통신 종류는 네 가지다.

| 종류 | 주고받는 것 | 메시지 (국내 표준) |
| --- | --- | --- |
| **V2I** 차 ↔ RSU | 차 위치, 신호·교차로 지도 | BSM, SPaT·MAP (KS R 1600-2, -3) |
| **V2P** 차 ↔ 보행자 | 보행자 스마트폰의 위치 | PSM (KS R 1600-6) |
| **V2N** 차 ↔ 교통센터 | 휴대폰망으로 위치 보고, 공사 구간 안내 | BSM, TIM (KS R 1600-5) |
| V2V 차 ↔ 차 | 차 위치 (방송만 하고 아직 쓰지 않음) | BSM |

차(OBU)는 V2X로 받은 정보만 보고 빨간불에 서고, 앞길에 나온 보행자 앞에 서고, 공사 구간에서 속도를 줄인다.

- [처음부터 설치하기](#처음부터-설치하기-windows-기준) — Windows에서 Ubuntu 설치부터 시뮬레이션 실행까지
- [실습: 적용 전·후 비교](#실습-적용-전후-비교) — V2I·V2P·V2N이 실제로 효과가 있는지 확인
- [다시 실행할 때](#다시-실행할-때) · [예전 버전을 설치했던 경우](#예전-버전을-설치했던-경우-업데이트)
- [문제 해결](#문제-해결)
- [전체 구조](#전체-구조) · [폴더 구조](#폴더-구조) · [보안 검증](#보안-검증-ieee-16092)

---

# 처음부터 설치하기 (Windows 기준)

위에서부터 순서대로 하면 된다. 처음 한 번은 2~3시간 걸린다 (대부분 다운로드와 OpenSCMS 빌드 시간).

**필요한 것**: Windows 10/11, RAM 32 GB 이상 권장(OpenSCMS 때문), 디스크 여유 60 GB 이상, 인터넷, GitHub 계정, SAE 계정(무료, 4단계에서 만듦)

**명령어 붙여 넣는 법**
- **PowerShell**(파란 창): `Ctrl + V` 또는 마우스 오른쪽 클릭
- **Ubuntu 창**(검은 창, `konel@...:~$` 같은 모양): **마우스 오른쪽 클릭** 또는 `Ctrl + Shift + V`
- 명령은 **한 블록씩** 붙여 넣고, 끝날 때까지 기다렸다가 다음으로 간다
- 비밀번호를 칠 때 화면에 아무것도 안 보이는 게 정상이다

---

## 1단계. Ubuntu 설치 (Windows)

### 1-1. WSL과 Ubuntu 설치

시작 메뉴에서 **PowerShell**을 찾아 **마우스 오른쪽 → 관리자 권한으로 실행**한 뒤:

```powershell
wsl --install -d Ubuntu-24.04
```

- 재부팅하라고 나오면 재부팅한다.
- 설치가 끝나면 Ubuntu 창이 뜨고 **사용자 이름**과 **비밀번호**를 정하라고 한다. 영어 소문자로 정하고 **비밀번호를 꼭 기억한다** (이후 `sudo` 할 때 계속 씀).
- Ubuntu 창이 안 뜨면 시작 메뉴에서 **Ubuntu 24.04 LTS** 를 연다.

### 1-2. 메모리 설정과 재시작

**Ubuntu 창**에서 (Windows 사용자 이름을 자동으로 찾아 설정 파일을 만든다):

```bash
WINUSER=$(cmd.exe /c "echo %USERNAME%" 2>/dev/null | tr -d '\r')
printf "[wsl2]\nmemory=24GB\n" > "/mnt/c/Users/$WINUSER/.wslconfig"
cat "/mnt/c/Users/$WINUSER/.wslconfig"
```

`[wsl2]`, `memory=24GB` 두 줄이 보이면 된다. (OpenSCMS가 메모리를 많이 쓴다. PC 메모리가 32 GB보다 작으면 `16GB`로 바꾼다) 이어서 systemd(서비스 관리자)가 켜져 있는지 확인한다:

```bash
ps -p 1 -o comm=
```

- `systemd`가 나오면 그대로 둔다.
- 다른 게 나오면 아래를 실행한다.
  ```bash
  echo -e "[boot]\nsystemd=true" | sudo tee -a /etc/wsl.conf
  ```

Ubuntu 창에서 `exit`로 나간 뒤, **PowerShell**에서:

```powershell
wsl --shutdown
```

> `wsl --shutdown`은 **PowerShell 명령**이다. Ubuntu 창에서 치면 `command not found`가 나온다.

시작 메뉴에서 **Ubuntu 24.04 LTS** 를 다시 열고 확인한다:

```bash
free -h
```

`Mem:` 줄의 total이 **23Gi** 정도면 성공 (16GB로 했으면 15Gi). **이제부터 모든 명령은 Ubuntu 창에서 한다.**

---

## 2단계. 개발 도구 설치 (Ubuntu)

### 2-1. Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
```

- 비밀번호를 물으면 1-1에서 정한 Ubuntu 비밀번호를 입력한다.
- 중간에 `WSL DETECTED: We recommend using Docker Desktop` 이 나오고 멈춘 것처럼 보여도 **Ctrl+C 누르지 말고 20초 기다린다.** 자동으로 계속된다.
- (이 프로젝트는 2차 보안 과제에서 iptables를 다루기 위해 Docker Desktop이 아니라 WSL 안에 Docker를 직접 설치한다.)

끝나면 권한을 주고 **창을 닫았다 다시 연다**:

```bash
sudo usermod -aG docker $USER
exit
```

Ubuntu를 다시 열고 확인:

```bash
docker run --rm hello-world
docker compose version
```

`Hello from Docker!` 와 `Docker Compose version ...` 이 나오면 성공.

### 2-2. SUMO, git, Python

```bash
sudo add-apt-repository -y ppa:sumo/stable
sudo apt update
sudo apt install -y sumo sumo-tools sumo-doc python3-venv git gh
```

- `503 Service Unavailable` 이 나오면 서버가 잠깐 바쁜 것이다. **같은 `sudo apt install ...` 줄을 다시 실행**하면 된다.

확인 (창이 뜨면 닫는다):

```bash
sumo --version | head -1
sumo-gui
```

### 2-3. Python 가상환경과 라이브러리

```bash
python3 -m venv ~/.venv/v2x
echo 'source ~/.venv/v2x/bin/activate' >> ~/.bashrc
source ~/.bashrc
pip install traci cryptography pycrate sumolib pyproj
python3 -c "import traci, cryptography, pycrate, sumolib, pyproj; print('OK')"
```

`OK` 가 나오면 성공. 프롬프트 앞에 `(v2x)` 가 붙어 있으면 가상환경이 켜진 것이다 (Ubuntu를 열 때마다 자동으로 켜짐).

---

## 3단계. 이 저장소 받기

### 3-1. GitHub 로그인

```bash
git config --global user.name "내 GitHub 아이디"
git config --global user.email "GitHub 가입 이메일"
gh auth login
```

질문에는 차례로 **GitHub.com → HTTPS → Y → Login with a web browser** 를 고른다.
`First copy your one-time code: XXXX-XXXX` 가 나오면 Enter를 누르고, **Windows 브라우저**에서 https://github.com/login/device 를 열어 코드를 입력하고 Authorize를 누른다.
(브라우저가 자동으로 안 열린다는 메시지는 무시해도 된다.) `✓ Logged in as ...` 가 나오면 성공.

### 3-2. 저장소 받기

```bash
cd ~
git clone https://github.com/konel0315/v2x-kr-testbed.git
cd ~/v2x-kr-testbed
ls
```

`README.md`, `obu`, `common`, `openscms-patch` 등이 보이면 성공.

---

## 4단계. SAE J2735 파일 준비

BSM·SPaT·MAP·PSM·TIM 메시지의 표준 설계도(ASN.1)다. **SAE 라이선스 때문에 저장소에는 넣지 않았다.** 팀원은 디스코드에 첨부한 파일을 받아 4번부터 하면 되고, 직접 받으려면 아래 1~3번을 따른다(무료).

1. Windows 브라우저에서 https://saemobilus.sae.org 에 가입하고 로그인한다.
2. 검색창에 `J2735 ASN` 을 검색한다.
3. **V2X Communications Message Set Dictionary™ ASN File — J2735ASN_202409** 를 열어 받는다. (자물쇠 아이콘이 아닌 항목. 결제 화면이 나오면 진행하지 않는다)
4. 받은 zip을 **Windows 다운로드 폴더**에서 압축 해제한다. (오른쪽 클릭 → 모두 압축 풀기)
   → `다운로드\J2735ASN_202409\J2735ASN_202409\V2X ASN.1 Module Collection 2024\` 안에 `.asn` 파일 43개가 생긴다.

Ubuntu에서 Python 변환기를 만든다:

```bash
cd ~/v2x-kr-testbed
WINUSER=$(cmd.exe /c "echo %USERNAME%" 2>/dev/null | tr -d '\r')
bash scripts/build_j2735.sh "/mnt/c/Users/$WINUSER/Downloads/J2735ASN_202409/J2735ASN_202409/V2X ASN.1 Module Collection 2024"
```

마지막에 `완료: .../common/j2735_gen.py` 가 나오면 성공.
`ASN 폴더를 찾을 수 없습니다` 가 나오면 압축 푼 위치가 다른 것이다. Windows 탐색기에서 `.asn` 파일들이 있는 폴더를 찾아 경로를 맞춘다 (`C:\Users\이름\...` 은 Ubuntu에서 `/mnt/c/Users/이름/...`).

---

## 5단계. V2X-Hub 설치 (RSU 소프트웨어)

미국 교통부의 RSU 소프트웨어다. 이 저장소에 포함하지 않고 따로 받는다.

### 5-1. 받기와 설치

```bash
cd ~
git clone --branch 8.1.0 https://github.com/usdot-fhwa-OPS/V2X-Hub.git
cd ~/V2X-Hub/configuration
echo "데이터 경로에 입력할 값: /home/$USER/v2xhub_data"
./initialization.sh
```

`detached HEAD` 안내는 무시한다. 질문에는 아래처럼 답한다 (**Enter**라고 적힌 것은 아무것도 치지 말고 Enter):

| 질문 (앞부분) | 답 |
| --- | --- |
| Enter V2X-Hub Version | Enter (8.1.0) |
| Enable Port Drayage | Enter |
| Enter Infrastructure id | Enter |
| **Enter an absolute file path to store V2X Hub Volumes** | ⚠️ 위에 출력된 **`/home/내아이디/v2xhub_data`** 를 그대로 입력 (기본값 `/tmp/...`는 재부팅 때 지워질 수 있고, 이후 명령이 모두 이 경로 기준) |
| Enter Infrastructure name | Enter |
| Enter V2XHub IP | Enter |
| Simulation Mode | Enter |
| MYSQL PASSWORD | 아무 비밀번호 (`; \| & < > $ ( ) * ?` 는 쓰지 않음) |
| V2X Hub Admin Username | Enter (`v2xadmin`) |
| **V2X Hub Admin Password** | ⚠️ **8~12자, 대문자·소문자·숫자·기호 각 1개 이상**. 기호는 `! . + _ * @ # ^ % ? ~ $ -` 중에서. 예: `Konel#2026`. **한/영 키가 영문인지 확인.** 꼭 기억해 둘 것 (웹 로그인에 씀) |
| Confirm password | 같은 비밀번호 |
| Are you sure you want to continue? | `y` |
| Would you like to generated local browser trusted certificates? | `n` |

- 비밀번호가 규칙에 안 맞으면 `INVALID PASSWORD`로 끝난다. `./initialization.sh` 를 처음부터 다시 실행한다.
- 마지막에 chromium 브라우저를 설치하다가 **멈추거나 실패하면** (WSL에서 흔함) `Ctrl+C` 후 직접 켠다:
  ```bash
  cd ~/V2X-Hub/configuration && sudo docker compose up -d
  ```

### 5-2. 실행 확인

```bash
cd ~/V2X-Hub/configuration
docker compose ps
```

`configuration-db-1`, `configuration-php-1`, `configuration-v2xhub-1` 세 줄의 STATUS가 모두 **`Up (healthy)`** 이면 성공.
(`starting` 이면 30초 뒤 다시 확인. `SAVE_STATE...` 경고는 무시)

### 5-3. 웹 화면 접속

**Windows 브라우저**(Chrome 또는 Edge)에서 **반드시 아래 순서로**:

1. `https://127.0.0.1:19760` 을 연다 → 경고 화면에서 **고급 → 127.0.0.1(안전하지 않음)(으)로 이동** → 빈 화면이 나와도 정상, 탭을 닫는다.
   (이걸 안 하면 로그인 후 `Connecting to wss://127.0.0.1:19760...` 이 계속 뜬다)
2. `https://127.0.0.1` 을 연다 → 같은 경고에서 **고급 → 이동**.
3. **Username** `v2xadmin`, **Password** 5-1에서 정한 웹 비밀번호로 로그인.

경고가 뜨는 이유: V2X-Hub가 스스로 만든 인증서를 써서 브라우저가 모르는 발급자라고 알리는 것이다. 내 컴퓨터 안의 화면이므로 진행해도 된다.

---

## 6단계. V2X-Hub 설정

### 6-1. 교차로 지도(MAP) 파일 만들기

```bash
sudo mkdir -p ~/v2xhub_data/download/MAP
sudo chown $USER ~/v2xhub_data/download/MAP
cd ~/v2x-kr-testbed
python3 tsc/make_map.py --out ~/v2xhub_data/download/MAP/pangyo_map.txt
```

`MAP 177바이트 -> ...pangyo_map.txt` 가 나오면 성공.

### 6-2. 플러그인 6개 켜기

웹 화면 **Plugins** 탭에서 한다. 플러그인 하나를 설정하는 방법:

1. **Filter Plugins** 줄에서 회색 **Disabled** 버튼을 누른다 (꺼진 플러그인 목록)
2. 플러그인 **이름(파란 줄)** 을 눌러 펼치고, 안의 **Configuration** 을 눌러 펼친다
3. 바꿀 **Key** 줄의 **Value 칸**을 클릭 → `Ctrl + A` 로 전부 지우고 → 아래 값을 붙여 넣는다 → **칸 바깥 빈 곳을 클릭**
4. **설정을 먼저 바꾼 다음에** 이름 왼쪽의 **작은 네모**를 눌러 켠다 (초록색이 됨)

| 플러그인 | 바꿀 Key | 값 |
| --- | --- | --- |
| **MessageReceiver** | (바꿀 것 없음) | 그냥 켠다 |
| **JSONMessageLoggerPlugin** | (바꿀 것 없음) | 그냥 켠다 |
| **SPAT** | `SignalGroupMapping` | 아래 ① |
| **MAP** | `MAP_Files` | 아래 ② |
| **ImmediateForward** | `ImmediateForwardConfigurations` | 아래 ③ |

① SPAT `SignalGroupMapping`
```
{"SignalGroups":[{"SignalGroupId":2,"Phase":2,"Type":"vehicle"},{"SignalGroupId":4,"Phase":4,"Type":"vehicle"},{"SignalGroupId":6,"Phase":6,"Type":"vehicle"},{"SignalGroupId":8,"Phase":8,"Type":"vehicle"}]}
```

② MAP `MAP_Files`
```
{"MapFiles":[{"Action":0,"FilePath":"/var/www/download/MAP/pangyo_map.txt"}]}
```

③ ImmediateForward `ImmediateForwardConfigurations` (기존 내용을 **통째로** 바꾼다)
```
[{"name":"Virtual Radio","rsuSpec":"RSU4.1","address":"host.docker.internal","port":1516,"txMode":"CONT","signMessages":false,"messages":[{"tmxType":"SPAT-P","sendType":"SPAT","psid":"0x8002","channel":183},{"tmxType":"MAP-P","sendType":"MAP","psid":"0xE0000017","channel":183}]}]
```

**확인**: 파란 **Enabled** 버튼을 누르면 **CommandPlugin, ImmediateForward, JSONMessageLoggerPlugin, MAP, MessageReceiver, SPAT** 6개가 모두 초록색이어야 한다.

> ⚠️ 이미 켠 뒤에 값을 바꿨다면 새 값이 반영되지 않을 수 있다. 그 플러그인의 **Disable** → 브라우저 `F5` → 값이 남아 있는지 확인 → 다시 켠다.

MAP이 파일을 제대로 읽었는지 확인:

```bash
cd ~/V2X-Hub/configuration && docker compose logs v2xhub --since 5m | grep -i "Failed to open"; cd ~/v2x-kr-testbed
```

아무것도 안 나오면 정상. `Failed to open file: .../MAP_9709_UPER.txt` 가 나오면 MAP 설정이 반영되지 않은 것이다 (위 ⚠️ 참고).

---

## 7단계. OpenSCMS 설치 (SCMS 인증 서버)

LG전자가 공개한 IEEE 1609.2.1 SCMS다. 등록 CA(ECA), 등록기관(RA), 응용 CA(ACA), 연결기관(LA) 2개, CAM이 각각 프로그램으로 떠서 실제 SCMS처럼 서로 통신하고, 루트 CA와 중간 CA(ICA)의 인증서는 설치할 때 한 번 만든다.
쿠버네티스(minikube) 위에서 돌아간다. 자세한 설명과 문제 해결: **[docs/openscms.md](docs/openscms.md)**

### 7-1. 필요한 프로그램

```bash
sudo apt install -y build-essential cmake pkg-config curl wget libssl-dev libzip-dev libcurl4-openssl-dev
```

쿠버네티스 도구(minikube, kubectl, helm, skaffold)는 `binenv`로 OpenSCMS가 정한 버전을 설치한다:

```bash
cd ~
wget -q -O binenv https://github.com/devops-works/binenv/releases/download/v0.19.0/binenv_linux_amd64
chmod +x ./binenv && ./binenv update && ./binenv install binenv && rm ./binenv
echo 'export PATH=$HOME/.binenv:$PATH' >> ~/.bashrc
source ~/.bashrc
```

### 7-2. OpenSCMS 받기와 우리 수정 적용

```bash
mkdir -p ~/openscms && cd ~/openscms
git clone --recurse-submodules https://github.com/OpenSCMS/OpenSCMS.git
cd ~/openscms/OpenSCMS
binenv install -l
bash ~/v2x-kr-testbed/openscms-patch/apply.sh
```

- `binenv install -l`: 이 폴더의 `.binenv.lock`에 적힌 버전으로 minikube·kubectl·helm·skaffold를 설치한다.
- `apply.sh`: 응용인증서에 **PSID 권한**(차·보행자 단말=BSM·PSM, RSU·교통센터=SPaT·MAP·TIM)을 넣도록 OpenSCMS를 고친다. 원래 OpenSCMS는 이 칸을 비워서 발급한다. 끝에 `적용 완료`가 세 번 나오면 성공. 되돌리기: `bash ~/v2x-kr-testbed/openscms-patch/revert.sh`

### 7-3. minikube 준비

```bash
minikube config set driver docker
(
  set -x; cd "$(mktemp -d)" &&
  KREW="krew-linux_amd64" &&
  curl -fsSLO "https://github.com/kubernetes-sigs/krew/releases/latest/download/${KREW}.tar.gz" &&
  tar zxvf "${KREW}.tar.gz" && ./"${KREW}" install krew
)
echo 'export PATH="$HOME/.krew/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
kubectl krew install rabbitmq
```

`kubectl krew list` 에 `rabbitmq`가 보이면 성공.

### 7-4. 기관 인증서 만들기, 빌드, 실행

```bash
cd ~/openscms/OpenSCMS
bash scripts/run_test_scms_manager.sh
ls certs
minikube start --memory=8g --cpus=4
skaffold run
```

- `ls certs`: `aca ctl eca ica ra rootca` 가 보이면 기관 인증서(루트·중간·등록·응용 CA, RA)가 만들어진 것이다.
- `skaffold run`: OpenSCMS(Rust)를 빌드해서 minikube에 올린다. **처음에는 20~40분** 걸린다. `Compiling ...` 이 계속 올라가면 정상이다.

끝나면 확인한다:

```bash
kubectl get pods
```

모든 줄이 `Running`, `1/1` 이면 성공 (처음엔 `ContainerCreating` 일 수 있으니 1~2분 뒤 다시 확인).
`skaffold run` 끝에 `deployment/ra-deployment failed ... exit code 101`(`Multiple CTL files found`)이 나와도, `ra-deployment`가 저절로 한 번 재시작된 뒤 `Running`이 되면 괜찮다 (OpenSCMS 시작 순서 문제, [문제 해결](#문제-해결) 참고).

### 7-5. 주소 연결과 인증서 발급 시험

```bash
cd ~/v2x-kr-testbed
bash scripts/openscms.sh start
bash scripts/build_ieee1609.sh
python3 scripts/provision.py
```

- `openscms.sh start`: ECA·RA·ACA를 `127.0.0.1:8091~8093`에 연결한다. 세 줄 모두 `200`이면 성공. 연결은 뒤에서 계속 유지된다.
- `build_ieee1609.sh`: OpenSCMS에 들어 있는 IEEE 1609.2 / 1609.2.1 정의(ASN.1)로 Python 변환기(`common/ieee1609_gen.py`)를 만든다.
- `provision.py`: OBU-01, OBU-02, 보행자 PED-01, RSU-01, 교통센터 TMC-01이 실제 SCMS 절차대로 인증서를 받는다. 아래처럼 나오면 성공:

```
[OBU-01] 등록 완료 (obu)
[OBU-01] 등록인증서 OK  id=...
[OBU-01] 응용인증서 발급  id=...
[OBU-01] 준비 완료: 인증서 ..., PSID ['0x20'], 발급자 ...
...
[PED-01] 준비 완료: 인증서 ..., PSID ['0x27'], 발급자 ...
[RSU-01] 준비 완료: 인증서 ..., PSID ['0x8002', '0xe0000017'], 발급자 ...
[TMC-01] 준비 완료: 인증서 ..., PSID ['0x8003'], 발급자 ...
신뢰 목록: root(...), ica(...), aca(...)
```

---

## 8단계. 실행

```bash
cd ~/v2x-kr-testbed
bash scripts/run.sh --coop
```

SUMO 창이 자동으로 뜨고 차 2대와 보행자(노란 점)가 움직인다. 터미널에는 OBU·보행자·교통센터 화면이 나온다:

```
[OBU-01] V2N: 교통센터 연결됨 (TLSv1.3)
[OBU-01] t= 14.0s 속도 13.89m/s | 신호 -  | 교차로 밖 | 보행자 경고: 앞 43.3m 옆 -4.8m | ... | 목표속도 ...
[OBU-01] t= 19.0s 속도  0.00m/s | 신호 -  | 교차로 밖 | 보행자 경고: 앞  4.1m 옆 +2.5m | ...
[OBU-02] t= 45.0s 속도  0.00m/s | 신호 RED | 차로 3 정지선까지   2.1m | ... | 목표속도 0.0
[OBU-02] t= 52.0s 속도  8.33m/s | 신호 -  | 교차로 밖 | 공사 구간 안: 권고 30 km/h (받은 경로 V2N+V2X) | ...
```

- **파란 차(OBU-01, V2I + V2P)**: 초록불에 교차로를 지난 뒤, 교차로 동쪽에서 **무단횡단하는 보행자**의 PSM을 받고 그 앞에 섰다가, 보행자가 다 건너면 출발한다. SUMO의 차는 이 보행자를 보지 못하게 해 두었으므로(가려진 보행자), 서는 것은 V2P 덕분이다.
- **빨간 차(OBU-02, V2I + V2N)**: V2X로 받은 빨간불에 정지선 앞에 섰다가 초록불에 출발하고, 교차로 북쪽 **공사 구간**에서는 교통센터가 휴대폰망(V2N)과 RSU(V2X) 두 경로로 보낸 안내대로 30 km/h로 줄인다.
- 협력주행 없이(`bash scripts/run.sh`) 돌리면 파란 차가 보행자 바로 옆을 그대로 지나가고 보행자 화면에 `위험!`이 찍힌다.
- 끝나면 `Ctrl + C` 로 모두 종료한다. 자세한 설명: [docs/v2p-v2n.md](docs/v2p-v2n.md)

**설치 완료.**

---

# 실습: 적용 전·후 비교

같은 장면을 V2X 기능을 켜고 끄며 비교한다. 각 실행은 **70초쯤 지나 차가 모두 도착하면 `Ctrl + C`** 로 끄고, 아래 확인 명령을 실행한다.
(`run.sh`를 다시 실행하면 `logs/`가 새로 만들어지므로 결과는 실행할 때마다 확인한다.)

### 실습 1. V2I — 빨간불 정지 (신호 정보 SPaT·MAP)

```bash
bash scripts/run.sh --coop        # 켬: 차가 V2X로 받은 신호만 보고 주행
grep -E "RED" logs/obu2.out | grep "0.00m/s" | head -2
```

- **켬**: 빨간 차가 `신호 RED | 정지선까지 2.1m`에서 `0.00m/s`로 선다.
- `bash scripts/run.sh`(협력주행 끔)로 돌리면 차는 SUMO 신호등을 따른다. 즉 V2X 없이도 서는데, 그건 SUMO가 신호등을 "본" 것이다. 협력주행에서는 SUMO 신호등을 무시하게 해 두었으므로 서는 이유가 V2X뿐이다.

### 실습 2. V2P — 무단횡단 보행자 (보행자 메시지 PSM)

```bash
bash scripts/run.sh --coop        # 켬
grep "보행자 경고" logs/obu1.out | head -2; grep "보행자 경고" logs/obu1.out | grep -m1 "0.00m/s"; grep 위험 logs/ped.out

bash scripts/run.sh               # 끔 (차가 V2X로 판단하지 않음)
grep 위험 logs/ped.out
```

- **켬**: 파란 차가 43 m 앞에서 보행자를 알고 줄이다가 보행자 4 m 앞에서 `0.00m/s`로 선다. `위험!` 줄은 없다.
- **끔**: `[PED-01] ... 위험! obu1가 0.7m 거리로 지나감 (속도 13.9m/s)`. SUMO의 차는 이 보행자를 못 보게 해 두었다(가려진 보행자).
- 보행자가 길을 안 건너면(`--coop --no-ped`) 차는 서지 않아야 한다. 차는 "보행자가 내 앞길 위에 있거나 지금 방향·속도로 2초 안에 들어오는가"만 보고 판단한다.

### 실습 3. V2N — 공사 구간 감속 (교통센터 TIM, 휴대폰망 + RSU)

```bash
bash scripts/run.sh --coop        # 켬
grep -E "t= *(5[0-9]|6[0-5])\.0s" logs/obu2.out | cut -c1-130
grep "V2N" logs/obu2.out | head -1; tail -3 logs/center.out

bash scripts/run.sh --coop --no-v2n   # 끔 (교통센터 없음)
grep -E "t= *(5[0-9]|6[0-5])\.0s" logs/obu2.out | cut -c1-130
```

- **켬**: 50~60초대 빨간 차 속도가 `8.33m/s`(30 km/h)이고 `공사 구간 안: 권고 30 km/h (받은 경로 V2N+V2X)`가 보인다. 첫 줄에 `V2N: 교통센터 연결됨 (TLSv1.3)`, 센터 화면에 `받은 위치 보고 ...`와 차의 익명 인증서 번호가 보인다.
- **끔**: 같은 시간에 `13m/s` 정도로 그냥 지나가고 `TIM 0/0`이다.

### 실습 4. 서명 검증 결과

```bash
for f in logs/*.jsonl; do echo "$f  통과 $(grep -c '"ACCEPT"' $f)  거부 $(grep -c '"REJECT"' $f)"; done
```

정상 실행이면 모든 파일이 **거부 0**이다. 가짜 메시지를 거부하는지(권한 없는 인증서, 변조, 서명 없음)는 [docs/v2p-v2n.md](docs/v2p-v2n.md)의 "시험으로 확인한 것"에 정리했다.

---

# 다시 실행할 때

컴퓨터를 다시 켠 뒤:

```bash
# 1) 시작 메뉴에서 Ubuntu 24.04 LTS 열기
# 2) V2X-Hub 켜기 (30초쯤 뒤 docker compose ps 로 healthy 확인)
cd ~/V2X-Hub/configuration && docker compose up -d

# 3) OpenSCMS 켜기 (minikube 시작 + 주소 연결, 1~3분)
cd ~/v2x-kr-testbed && bash scripts/openscms.sh start

# 4) (선택) VS Code로 코드 열기
cd ~/v2x-kr-testbed && code .

# 5) 시뮬레이션 (인증서가 있으면 재사용, 만료됐으면 새로 받음)
cd ~/v2x-kr-testbed
bash scripts/run.sh --coop
```

| 명령 | 용도 |
| --- | --- |
| `bash scripts/run.sh --coop` | 전체 실행 (V2X로 받은 신호·보행자·공사 안내로 협력주행) |
| `bash scripts/run.sh --coop --no-ped` | 보행자가 길을 건너지 않음 |
| `bash scripts/run.sh --coop --no-v2n` | 교통센터 없이 (V2N 끔) |
| `bash scripts/run.sh` | 전체 실행 (차는 SUMO 신호를 따름, V2X 메시지만 주고받음) |
| `sumo-gui -c sumo/intersection.sumocfg` | SUMO 화면만 보기 (V2X 없음) |
| 브라우저 `https://127.0.0.1` | V2X-Hub 웹 관리 화면 (v2xadmin) |
| `cd ~/V2X-Hub/configuration && docker compose stop` | V2X-Hub 끄기 (설정은 유지) |
| `bash scripts/openscms.sh status` | OpenSCMS 기관 상태와 주소 연결 확인 |
| `python3 scripts/provision.py --renew` | 응용인증서 새로 받기 |
| `minikube stop` | OpenSCMS 끄기 (데이터는 유지) |

**출력 위치**: `logs/*.out`(각 프로그램 화면), `logs/*.jsonl`(메시지마다 JSON 한 줄), `~/v2xhub_data/logs/json/`(V2X-Hub가 받은 BSM 기록)

**VS Code 처음 쓸 때**: Windows에 VS Code를 설치하고, 확장(`Ctrl+Shift+X`)에서 **WSL**(Microsoft)을 설치한 뒤 `code .` 로 연다. 왼쪽 아래에 `WSL: Ubuntu-24.04` 가 보여야 한다. "Restricted Mode" 가 뜨면 **Manage → Trust** 를 누르고, **Python**·**Pylance** 확장을 "Install in WSL" 로 설치한다.

---

# 예전 버전을 설치했던 경우 (업데이트)

이미 설치해 둔 PC에서 새 버전(OpenSCMS, V2P, V2N)을 받을 때:

```bash
cd ~/v2x-kr-testbed && git checkout master && git pull
```

그다음 어디까지 설치했느냐에 따라:

- **7단계(OpenSCMS)를 아직 안 했다** → [7단계](#7단계-openscms-설치-scms-인증-서버)부터 하면 된다.
- **7단계를 이미 했다** (수정본 일부만 적용된 상태):
  ```bash
  bash ~/v2x-kr-testbed/openscms-patch/apply.sh
  cd ~/openscms/OpenSCMS && minikube start --memory=8g --cpus=4 && skaffold run
  kubectl rollout restart deployment/ra-deployment
  sleep 60 && kubectl get pods
  cd ~/v2x-kr-testbed && bash scripts/openscms.sh start && bash scripts/build_ieee1609.sh && python3 scripts/provision.py
  ```
  `apply.sh`에서 `이미 적용됨`은 그대로 두고 새 것만 적용한다. `provision.py`에 `PED-01 ... ['0x27']`, `TMC-01 ... ['0x8003']`가 나오면 끝.

---

# 문제 해결

| 증상 | 원인 | 해결 |
| --- | --- | --- |
| Ubuntu에서 `wsl: command not found` | `wsl`은 Windows 명령 | PowerShell에서 실행 |
| Docker 설치가 `WSL DETECTED` 에서 멈춤 | 20초 대기 안내 | 기다리면 계속됨 |
| `docker: permission denied` | docker 권한이 아직 적용 안 됨 | Ubuntu 창을 닫았다 다시 열기 |
| SUMO 설치 중 `503 Service Unavailable` | 배포 서버 일시 장애 | 같은 `apt install` 다시 실행 |
| V2X-Hub 설치 `INVALID PASSWORD` | 웹 비밀번호 규칙 위반 | 8~12자, 대·소문자·숫자·기호. 한/영 확인 후 다시 실행 |
| V2X-Hub 설치가 chromium에서 멈춤 | WSL에서 브라우저 설치 실패 | Ctrl+C 후 `sudo docker compose up -d` |
| 브라우저 "연결이 비공개로 설정되어 있지 않습니다" | V2X-Hub 자체 서명 인증서 | 고급 → 이동 |
| 로그인 후 `Connecting to wss://127.0.0.1:19760` 반복 | 19760 포트 인증서 미허용 | 새 탭에서 `https://127.0.0.1:19760` 열어 허용 후 `https://127.0.0.1` 로 재접속 |
| 플러그인 목록에 CommandPlugin만 보임 | 필터가 Enabled | Disabled 필터를 눌러 꺼진 플러그인 보기 |
| `make_map.py` 에서 `PermissionError` | MAP 폴더가 Docker(root) 소유 | 6-1의 `sudo mkdir`, `sudo chown` 먼저 |
| OBU 화면에 `MAP 0`, 신호 `UNKNOWN` | MAP 플러그인이 옛 설정으로 실행 중 | MAP Disable → F5 → 값 확인 → 다시 켜기 |
| `build_j2735.sh` 에서 `ASN 폴더를 찾을 수 없습니다` | 압축 푼 경로가 다름 | `.asn` 파일이 있는 폴더 경로로 다시 실행 |
| `ModuleNotFoundError: common.j2735_gen` | 4단계를 안 함 | 4단계 실행 |
| `ModuleNotFoundError` (traci, pycrate 등) | 가상환경이 꺼져 있음 | `source ~/.venv/v2x/bin/activate` |
| `OpenSCMS(RA 127.0.0.1:8092)에 연결할 수 없습니다` | OpenSCMS가 꺼져 있거나 주소 연결이 끊김 | `bash scripts/openscms.sh start` |
| `응용인증서에 PSID ... 권한이 없습니다` | OpenSCMS 수정본이 빌드되지 않음 | 7-2의 `apply.sh` 후 `cd ~/openscms/OpenSCMS && skaffold run` |
| `HTTP 400 400-21` (unregistered) | OpenSCMS를 새로 설치해서 예전 등록이 없어짐 | `python3 scripts/provision.py --reset` |
| `ModuleNotFoundError: common.ieee1609_gen` | 7-5를 안 함 | `bash scripts/build_ieee1609.sh` |
| 그 밖의 OpenSCMS 문제 | | [docs/openscms.md](docs/openscms.md) 문제 해결 |
| `[PED-01] 실패: ... 400-30` 또는 `[TMC-01] 실패: ... 400-30` | OpenSCMS가 PSM·TIM 권한을 아직 허용하지 않음 | `bash openscms-patch/apply.sh` 후 `cd ~/openscms/OpenSCMS && skaffold run && kubectl rollout restart deployment/ra-deployment` |
| OBU 화면에 `TIM 0/0` | 교통센터가 꺼져 있음 | `logs/center.out` 확인 |
| `skaffold run`에서 `ra-deployment failed ... exit code 101`, 로그에 `Multiple CTL files found` | RA 프로그램 두 개가 동시에 켜지며 신뢰 목록을 두 번 적음 (OpenSCMS 문제) | 1분 기다려 `kubectl get pods`에서 `ra-deployment`가 `Running`이면 해결. 계속 `CrashLoopBackOff`면 `kubectl scale deployment/ra-deployment --replicas=0; sleep 5; kubectl scale deployment/ra-deployment --replicas=1` |
| 보행자(노란 점)가 SUMO 화면에 안 보임 | 화면이 너무 작음 | SUMO 화면에서 교차로 동쪽을 확대 |
| `Address already in use` | 이전 실행 프로그램이 남아 있음 | `pkill -f "radio/air.py\|rsu-gateway\|rsu-signer\|tsc/tsc.py\|obu/obu.py\|ped/ped.py\|center/center.py"; pkill sumo-gui` 후 다시 실행 |
| VS Code에서 만든 파일이 0바이트 | 저장 안 함 | `Ctrl + S` |

---

# 전체 구조

```
        OpenSCMS (minikube): 루트 → ICA → ECA·ACA, RA      ← 모든 장치가 처음에 인증서를 받음 (IEEE 1609.2.1)
   ┌──────────────┬──────────────┬─────────────────────┬──────────────┐
 OBU-01, OBU-02   PED-01         RSU-01                TMC-01
 차 (obu.py)      보행자 폰        gateway.py             교통센터
                 (ped.py)       + V2X-Hub + signer.py  (center.py)

 가상 무선 (V2X, air.py)    차 ⇄ RSU: BSM / SPaT·MAP     보행자 → 차·RSU: PSM     RSU → 차: TIM
 휴대폰망 (V2N, TLS 1.3)    차 ⇄ 교통센터: BSM(위치 보고) / TIM(공사 안내)
 유선 (RSU 백홀)            교통센터 → RSU: TIM          신호제어기 tsc.py → V2X-Hub: TSCBM
 SUMO                      차·보행자 움직임 ↔ obu.py·ped.py,  신호 → tsc.py
```

- **차 → RSU**: OBU가 BSM을 서명해 방송 → RSU 게이트웨이가 검증 → V2X-Hub
- **RSU → 차**: V2X-Hub가 SPaT·MAP 생성 → RSU 서명기가 서명해 방송 → OBU가 검증 → 신호에 따라 정지·출발
- **보행자 → 차 (V2P)**: 보행자 스마트폰이 PSM을 서명해 직접 방송 → OBU가 검증 → 앞길 위(또는 2초 안에 들어올) 보행자면 그 앞에 정지. RSU도 받아 검증한 뒤 V2X-Hub로 넘긴다.
- **차 ↔ 교통센터 (V2N)**: OBU가 휴대폰망(TLS 1.3)으로 1초마다 서명된 BSM을 올리고, 센터가 서명한 공사 안내 TIM을 내려받는다. 센터는 같은 TIM을 RSU에도 넘겨 직접통신으로도 방송한다(하이브리드). 어느 경로로 와도 OBU는 똑같이 검증한다.
- V2X-Hub는 RSU의 메시지 처리기이며 서명·검증 기능이 없어서, 앞에 검증 게이트웨이, 뒤에 서명기를 둔다.
- **인증서**: 각 장치가 OpenSCMS에 등록 → 등록인증서(ECA) → 응용인증서 요청(RA, 암호화) → 다운로드. 응용인증서는 ACA가 발급하고 장치 이름이 없는 익명 인증서다.
- Docker 위에는 V2X-Hub와 OpenSCMS(minikube)가 있고, 나머지는 Ubuntu에서 일반 프로그램으로 실행된다 (`scripts/run.sh`가 한 번에 실행).

## 한국 기준과 구현

| 계층 | 기준 | 근거 | 이 환경에서 |
| --- | --- | --- | --- |
| 무선 | LTE-V2X | 과기정통부·국토부 2023.12 | 가상 무선 채널(UDP)로 대신 — `radio/air.py` |
| 메시지 | SPaT, MAP, BSM (SAE J2735) | KS R 1600 | SAE J2735 2024 UPER — `common/j2735.py` |
| 메시지 봉투 | IEEE 1609.3 WSMP | | `common/wsmp.py` |
| 서명 | IEEE 1609.2-2022 | CTI 4001, 항법학회지 2023 | 명시적 응용인증서, ECDSA P-256 — `common/sec1609.py` |
| 인증 체계 | SCMS (IEEE 1609.2.1-2022) | 자동차안전학회지 2021 | OpenSCMS: 루트 → ICA → ECA·ACA, RA — `common/scms_client.py` |
| RSU 소프트웨어 | V2X-Hub (미국 교통부) | V2X-Hub README | V2X-Hub 8.1.0 (Docker) |
| 신호제어기 → RSU | NTCIP 1202 | | TSCBM — `tsc/tsc.py` |
| V2P 메시지 | PSM | KS R 1600-6 | 보행자 단말이 직접 방송, PSID 0x27 — `ped/ped.py` |
| V2N 방식 | 하이브리드 (V2X + 상용망) | 국토부 2022.9.23 | 휴대폰망(TCP로 흉내) + RSU 두 경로 — `center/center.py`, `common/v2n.py` |
| V2N 메시지 | 여행자 정보 TIM | KS R 1600-5 | 공사 구간 안내, PSID 0x8003 |
| 센터 통신 보호 | TLS 보안 채널 | TTAK.KO-12.0432 | TLS 1.3 + 메시지 서명 유지 |

# 폴더 구조

```
obu/obu.py               OBU (같은 코드로 OBU-01, OBU-02). BSM 서명·방송, SPaT·MAP·PSM·TIM 검증, 협력주행, 휴대폰망 접속
ped/ped.py               보행자 스마트폰 (PED-01): SUMO 보행자 각본 + PSM 서명·방송 (V2P)
center/center.py         교통센터 (TMC-01): 휴대폰망 서버(TLS), 위치 보고 수신, 공사 안내 TIM (V2N)
rsu-gateway/gateway.py   RSU 수신: BSM·PSM 검증 → V2X-Hub (UDP 26789)
rsu-signer/signer.py     RSU 송신: V2X-Hub 출력(UDP 1516) → 서명 → 방송. 센터가 서명한 TIM(UDP 1517)은 확인 후 그대로 방송
tsc/tsc.py               가상 신호제어기: SUMO 신호 → TSCBM → V2X-Hub (UDP 6053)
tsc/make_map.py          SUMO 도로 → J2735 MAP 파일
radio/air.py             가상 무선 채널 (방송, 손실·지연 옵션)
common/                  공통 부품
  j2735.py               BSM·SPaT·MAP·PSM·TIM 생성·해석
  v2n.py                 휴대폰망 흉내: TLS 1.3 연결, 시험용 TLS 인증서 생성
  geo.py                 위치 계산 (내 진행 방향 기준 앞·옆 거리)
  sec1609.py             IEEE 1609.2 인증서·서명·검증 (검증 4단계)
  scms_client.py         IEEE 1609.2.1 단말 쪽: 등록, 등록인증서, 응용인증서 요청·다운로드
  scms_crypto.py         ECIES·AES-CCM 암호화, 암묵적 인증서 키 복원
  identity.py            장치별 인증서·신뢰 목록 준비 (OBU=BSM, 보행자=PSM, RSU=SPaT·MAP, 센터=TIM)
  wsmp.py, psid.py       메시지 봉투, 메시지 종류 번호
  intersection.py        MAP·SPaT 해석 (차로, 정지선 거리, 신호 색)
  radio.py, v2xlog.py    가상 무선 접속, 메시지별 JSON 로그
sumo/                    사거리 1개(판교 부근 가상 좌표), 차량 2대 (보행자는 ped.py가 추가)
scripts/run.sh           전체 실행
scripts/openscms.sh      OpenSCMS 켜기(minikube)·주소 연결·상태 확인
scripts/provision.py     OBU·RSU 인증서 받기 (OpenSCMS)
scripts/build_ieee1609.sh IEEE 1609.2/1609.2.1 ASN.1 → Python 변환기
openscms-patch/          OpenSCMS 수정본 (응용인증서 PSID 권한, RA의 장치별 PSID 정책)
ee-data/                 장치 키·인증서 (Git 제외)
center/tls/              교통센터 TLS 인증서·키 (처음 실행 때 생성, Git 제외)
scripts/setup_ubuntu.sh  개발 도구 설치 (2단계를 한 번에)
scripts/build_j2735.sh   SAE J2735 ASN.1 → Python 변환기
v2xhub-config/           V2X-Hub 플러그인 설정 기록
docs/                    계획서, 단계별 기록
```

# 보안 검증 (IEEE 1609.2)

받는 쪽(RSU 게이트웨이·서명기, OBU, 교통센터)은 아래 순서로 확인하고, 하나라도 실패하면 버리고 기록한다. 직접통신(V2X)으로 받든 휴대폰망(V2N)으로 받든 같다.

| 단계 | 검사 | 실패 이유 |
| --- | --- | --- |
| 1 | 서명 | UNSIGNED, BAD_SIGNATURE |
| 2 | 권한: 메시지 PSID가 인증서에 있는가 (OBU=BSM, 보행자=PSM, RSU=SPaT·MAP, 센터=TIM) | NO_PERMISSION |
| 3 | 유효기간 | CERT_EXPIRED |
| 4 | 발급 체인: 신뢰하는 루트까지 이어지는가 | UNKNOWN_ISSUER |

인증서 형식과 서명·검증은 IEEE 1609.2를, 인증서 발급 절차는 IEEE 1609.2.1을 따른다 (OpenSCMS). 자세한 내용: [docs/openscms.md](docs/openscms.md)

# 단계별 기록

| 단계 | 내용 | 문서 |
| --- | --- | --- |
| 0 | 개발 환경 | [docs/setup.md](docs/setup.md) |
| 1 | V2X-Hub BSM 수신 | [docs/step1.md](docs/step1.md) |
| 2 | OBU 2대 BSM 전송 | [docs/step2.md](docs/step2.md) |
| 3, 3-1 | RSU SPaT·MAP 방송, 협력주행 | [docs/step3.md](docs/step3.md) |
| 4~6 | 서명·검증 (처음에는 자체 CA) | [docs/step4-6.md](docs/step4-6.md) |
| 8 | OpenSCMS로 교체 (IEEE 1609.2.1) | [docs/openscms.md](docs/openscms.md) |
| 9 | V2P(보행자), V2N(교통센터·하이브리드) | [docs/v2p-v2n.md](docs/v2p-v2n.md) |

# 단순화한 점과 앞으로

- 무선은 가상(UDP). 응용인증서는 NonButterfly 방식으로 장치당 1장 (실제 OBU는 버터플라이 키로 여러 장을 받아 바꿔 씀)
- SCMS 통신은 HTTP (요청 내용은 1609.2.1대로 서명·암호화되지만, 전송 구간 TLS와 OAuth 토큰은 생략)
- 루트 인증서는 장치 출고 때 넣는 것으로 보고, OpenSCMS 폴더에서 한 번 복사해 쓴다 (`ee-data/trust/root.cert`)
- RSU·OBU는 일반 프로그램으로 실행 (V2X-Hub와 OpenSCMS만 컨테이너)
- 보행자는 각본대로 움직이는 1명이고, SUMO 화면에는 점(POI)으로 표시한다. 휴대폰망은 내 PC 안의 TCP 연결로 흉내 내고, 교통센터 → RSU 구간(UDP)은 보호하지 않는다
- 차는 다른 차의 BSM을 받지만 아직 쓰지 않는다 (V2V 응용은 없음)
- 2차 과제(추가 보안): 재전송 검사, 시각 교차 검사, SPaT 개연성 검사, 위치 대조, 속도 제한, CRL, 인증서 자동 갱신·익명 교체, HSM, HTTPS, Docker 네트워크 분리 + iptables

# 사용한 오픈소스

- [V2X-Hub](https://github.com/usdot-fhwa-OPS/V2X-Hub) (Apache 2.0) — 저장소에 포함하지 않고 별도 설치
- [Eclipse SUMO](https://eclipse.dev/sumo/)
- [OpenSCMS](https://github.com/OpenSCMS/OpenSCMS) (Apache 2.0, LG전자) — IEEE 1609.2.1 SCMS. 저장소에 포함하지 않고 별도 설치, 수정분만 `openscms-patch/`에
- [pycrate](https://github.com/pycrate-org/pycrate) — ASN.1 컴파일·인코딩
- [cryptography](https://cryptography.io/) — ECDSA P-256, ECDH, AES-CCM
- SAE J2735 ASN.1 (J2735ASN_202409) — SAE 라이선스, 저장소에 포함하지 않음 (각자 SAE에서 받기)
