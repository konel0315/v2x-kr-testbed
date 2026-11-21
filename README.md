# V2X 가상환경 (한국 C-ITS 기준) — RSU 1, OBU 2, CA 1

국내 C-ITS 표준을 전제로 V2X 통신의 기본 보안(IEEE 1609.2 서명·검증)을 오픈소스 가상환경에서 구현한다.
모든 메시지는 서명되고, 받는 쪽은 검증을 통과한 메시지만 쓴다.
차(OBU)는 V2X로 받은 신호만 보고 빨간불에 서고 초록불에 출발한다.

- [처음부터 설치하기](#처음부터-설치하기-windows-기준) — Windows에서 Ubuntu 설치부터 시뮬레이션 실행까지
- [다시 실행할 때](#다시-실행할-때)
- [문제 해결](#문제-해결)
- [전체 구조](#전체-구조) · [폴더 구조](#폴더-구조) · [보안 검증](#보안-검증-ieee-16092)

---

# 처음부터 설치하기 (Windows 기준)

위에서부터 순서대로 하면 된다. 처음 한 번은 1~2시간 걸린다 (대부분 다운로드 시간).

**필요한 것**: Windows 10/11, RAM 16 GB 이상 권장, 디스크 여유 30 GB 이상, 인터넷, GitHub 계정, SAE 계정(무료, 4단계에서 만듦)

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
printf "[wsl2]\nmemory=8GB\n" > "/mnt/c/Users/$WINUSER/.wslconfig"
cat "/mnt/c/Users/$WINUSER/.wslconfig"
```

`[wsl2]`, `memory=8GB` 두 줄이 보이면 된다. 이어서 systemd(서비스 관리자)가 켜져 있는지 확인한다:

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

`Mem:` 줄의 total이 **7~8Gi** 정도면 성공. **이제부터 모든 명령은 Ubuntu 창에서 한다.**

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

`README.md`, `obu`, `ca`, `common` 등이 보이면 성공.

---

## 4단계. SAE J2735 파일 준비

BSM·SPaT·MAP 메시지의 표준 설계도(ASN.1)다. **SAE 라이선스 때문에 저장소에 넣지 않았으므로 각자 받는다.** (무료)

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

## 7단계. 실행

```bash
cd ~/v2x-kr-testbed
bash scripts/run.sh --coop
```

SUMO 창이 자동으로 뜨고 차 2대가 움직인다. 터미널에는 OBU 화면이 나온다:

```
[OBU-02] 인증서 받음: PSID ['0x20']
[OBU-02] MAP 수신: 이제 V2X 신호만 보고 주행
[OBU-02] t= 20.0s 속도  0.00m/s | 신호 RED     | 차로 3 정지선까지   2.1m | 받은 SPaT 199 MAP 20 | 목표속도 0.0
[OBU-02] t= 46.0s 속도  1.66m/s | 신호 GREEN   | 차로 3 정지선까지   1.4m | 받은 SPaT 458 MAP 47
```

- **파란 차(OBU-01)** 는 초록불에 통과한다.
- **빨간 차(OBU-02)** 는 SUMO 신호등은 무시한 채 **V2X로 받은 빨간불만 보고** 정지선 앞에 섰다가, 초록불에 출발한다.
- 끝나면 `Ctrl + C` 로 모두 종료한다.

**설치 완료.**

---

# 다시 실행할 때

컴퓨터를 다시 켠 뒤:

```bash
# 1) 시작 메뉴에서 Ubuntu 24.04 LTS 열기
# 2) V2X-Hub 켜기 (30초쯤 뒤 docker compose ps 로 healthy 확인)
cd ~/V2X-Hub/configuration && docker compose up -d

# 3) (선택) VS Code로 코드 열기
cd ~/v2x-kr-testbed && code .

# 4) 시뮬레이션
cd ~/v2x-kr-testbed
bash scripts/run.sh --coop
```

| 명령 | 용도 |
| --- | --- |
| `bash scripts/run.sh --coop` | 전체 실행 (V2X 신호로 협력주행) |
| `bash scripts/run.sh` | 전체 실행 (차는 SUMO 신호를 따름, V2X 메시지만 주고받음) |
| `sumo-gui -c sumo/intersection.sumocfg` | SUMO 화면만 보기 (V2X 없음) |
| 브라우저 `https://127.0.0.1` | V2X-Hub 웹 관리 화면 (v2xadmin) |
| `cd ~/V2X-Hub/configuration && docker compose stop` | V2X-Hub 끄기 (설정은 유지) |

**출력 위치**: `logs/*.out`(각 프로그램 화면), `logs/*.jsonl`(메시지마다 JSON 한 줄), `~/v2xhub_data/logs/json/`(V2X-Hub가 받은 BSM 기록)

**VS Code 처음 쓸 때**: Windows에 VS Code를 설치하고, 확장(`Ctrl+Shift+X`)에서 **WSL**(Microsoft)을 설치한 뒤 `code .` 로 연다. 왼쪽 아래에 `WSL: Ubuntu-24.04` 가 보여야 한다. "Restricted Mode" 가 뜨면 **Manage → Trust** 를 누르고, **Python**·**Pylance** 확장을 "Install in WSL" 로 설치한다.

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
| OBU가 `CA 거부` 또는 연결 오류 | CA가 늦게 켜짐 / 이전 실행이 남아 있음 | Ctrl+C로 끄고 `bash scripts/run.sh --coop` 다시 |
| `Address already in use` | 이전 실행 프로그램이 남아 있음 | `pkill -f "ca/ca.py\|radio/air.py\|rsu-gateway\|rsu-signer\|tsc/tsc.py\|obu/obu.py"; pkill sumo-gui` 후 다시 실행 |
| VS Code에서 만든 파일이 0바이트 | 저장 안 함 | `Ctrl + S` |

---

# 전체 구조

```
                    CA (인증서 발급)
                 ┌────────┼────────┐
                 ▼        ▼        ▼
 SUMO ──위치──▶ OBU-01  OBU-02    RSU-01 = gateway.py + V2X-Hub + signer.py
 (교차로·차)      │ ▲      │ ▲         ▲ BSM(검증)      │ SPaT·MAP(서명)
      ▲          │ │      │ │         │                ▼
      └─정지/출발┘ └──────┴─┴═══ 가상 무선 (air.py) ═══┘
 SUMO 신호 ──▶ tsc.py ──▶ V2X-Hub SPaT 플러그인
```

- **차 → RSU**: OBU가 BSM을 서명해 방송 → RSU 게이트웨이가 검증 → V2X-Hub
- **RSU → 차**: V2X-Hub가 SPaT·MAP 생성 → RSU 서명기가 서명해 방송 → OBU가 검증 → 신호에 따라 정지·출발
- V2X-Hub는 RSU의 메시지 처리기이며 서명·검증 기능이 없어서, 앞에 검증 게이트웨이, 뒤에 서명기를 둔다.
- Docker 위에는 V2X-Hub만 있고, 나머지는 Ubuntu에서 일반 프로그램으로 실행된다 (`scripts/run.sh`가 한 번에 실행).

## 한국 기준과 구현

| 계층 | 기준 | 근거 | 이 환경에서 |
| --- | --- | --- | --- |
| 무선 | LTE-V2X | 과기정통부·국토부 2023.12 | 가상 무선 채널(UDP)로 대신 — `radio/air.py` |
| 메시지 | SPaT, MAP, BSM (SAE J2735) | KS R 1600 | SAE J2735 2024 UPER — `common/j2735.py` |
| 메시지 봉투 | IEEE 1609.3 WSMP | | `common/wsmp.py` |
| 서명 | IEEE 1609.2 | CTI 4001, 항법학회지 2023 | 명시적 인증서, ECDSA P-256 — `common/sec1609.py` |
| 인증 체계 | SCMS 구조 | 자동차안전학회지 2021 | 루트 → 등록 CA·응용 CA — `ca/ca.py` |
| RSU 소프트웨어 | V2X-Hub (미국 교통부) | V2X-Hub README | V2X-Hub 8.1.0 (Docker) |
| 신호제어기 → RSU | NTCIP 1202 | | TSCBM — `tsc/tsc.py` |

# 폴더 구조

```
ca/ca.py                 CA 서버 (등록 인증서, 응용 인증서, 체인 배포). 키는 ca/data/ (Git 제외)
obu/obu.py               OBU (같은 코드로 OBU-01, OBU-02). BSM 서명·방송, SPaT·MAP 검증, 협력주행
rsu-gateway/gateway.py   RSU 수신: BSM 검증 → V2X-Hub (UDP 26789)
rsu-signer/signer.py     RSU 송신: V2X-Hub 출력(UDP 1516) → 서명 → 방송
tsc/tsc.py               가상 신호제어기: SUMO 신호 → TSCBM → V2X-Hub (UDP 6053)
tsc/make_map.py          SUMO 도로 → J2735 MAP 파일
radio/air.py             가상 무선 채널 (방송, 손실·지연 옵션)
common/                  공통 부품
  j2735.py               BSM·SPaT·MAP 생성·해석
  sec1609.py             IEEE 1609.2 인증서·서명·검증 (검증 4단계)
  identity.py            장치 시작 시 CA에서 인증서 받기
  wsmp.py, psid.py       메시지 봉투, 메시지 종류 번호
  intersection.py        MAP·SPaT 해석 (차로, 정지선 거리, 신호 색)
  radio.py, v2xlog.py    가상 무선 접속, 메시지별 JSON 로그
sumo/                    사거리 1개(판교 부근 가상 좌표), 차량 2대
scripts/run.sh           전체 실행
scripts/setup_ubuntu.sh  개발 도구 설치 (2단계를 한 번에)
scripts/build_j2735.sh   SAE J2735 ASN.1 → Python 변환기
v2xhub-config/           V2X-Hub 플러그인 설정 기록
docs/                    계획서, 단계별 기록
```

# 보안 검증 (IEEE 1609.2)

받는 쪽(RSU 게이트웨이, OBU)은 아래 순서로 확인하고, 하나라도 실패하면 버리고 기록한다.

| 단계 | 검사 | 실패 이유 |
| --- | --- | --- |
| 1 | 서명 | UNSIGNED, BAD_SIGNATURE |
| 2 | 권한: 메시지 PSID가 인증서에 있는가 (OBU=BSM, RSU=SPaT·MAP) | NO_PERMISSION |
| 3 | 유효기간 | CERT_EXPIRED |
| 4 | 발급 체인: 신뢰하는 루트까지 이어지는가 | UNKNOWN_ISSUER |

인증서 형식과 서명·검증은 IEEE 1609.2를 따르고, 인증서 발급 절차(IEEE 1609.2.1)는 단순화했다. 자세한 내용: [docs/step4-6.md](docs/step4-6.md)

# 단계별 기록

| 단계 | 내용 | 문서 |
| --- | --- | --- |
| 0 | 개발 환경 | [docs/setup.md](docs/setup.md) |
| 1 | V2X-Hub BSM 수신 | [docs/step1.md](docs/step1.md) |
| 2 | OBU 2대 BSM 전송 | [docs/step2.md](docs/step2.md) |
| 3, 3-1 | RSU SPaT·MAP 방송, 협력주행 | [docs/step3.md](docs/step3.md) |
| 4~6 | CA, 서명·검증 | [docs/step4-6.md](docs/step4-6.md) |

# 단순화한 점과 앞으로

- 무선은 가상(UDP), 인증서는 명시적·1장 고정, CA는 3개 기관으로 단순화, CA 통신은 HTTP
- RSU·OBU·CA는 일반 프로그램으로 실행 (V2X-Hub만 Docker)
- **예정**: CA를 오픈소스 SCMS(OpenSCMS, IEEE 1609.2.1)로 교체. `ca/ca.py`와 `common/identity.py`만 바꾸면 되도록 나눠 둠
- 2차 과제(추가 보안): 재전송 검사, 시각 교차 검사, SPaT 개연성 검사, 위치 대조, 속도 제한, CRL, 인증서 자동 갱신·익명 교체, HSM, HTTPS, Docker 네트워크 분리 + iptables

# 사용한 오픈소스

- [V2X-Hub](https://github.com/usdot-fhwa-OPS/V2X-Hub) (Apache 2.0) — 저장소에 포함하지 않고 별도 설치
- [Eclipse SUMO](https://eclipse.dev/sumo/)
- [pycrate](https://github.com/pycrate-org/pycrate) — ASN.1 컴파일·인코딩 (IEEE 1609.2 ASN.1 포함)
- [cryptography](https://cryptography.io/) — ECDSA P-256
- SAE J2735 ASN.1 (J2735ASN_202409) — SAE 라이선스, 저장소에 포함하지 않음 (각자 SAE에서 받기)
