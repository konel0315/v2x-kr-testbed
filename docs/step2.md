# 2단계: SUMO 차량 2대 → OBU → J2735 BSM → V2X-Hub

## 결과: 통과 (2026-11-19)
OBU 2대가 SUMO 차량 상태로 J2735(2024) BSM을 10 Hz로 만들어 V2X-Hub MessageReceiver(UDP 26789)로 전송.
V2X-Hub JSON 로그에서 OBU2(id 4F425532 = "OBU2")의 위치 lat 374000887, long 1271100180 (판교 부근 교차로 북쪽) 확인.

## 구성
- sumo/: 사거리 1개 (경도·위도 좌표, UTM 투영), 차량 obu1(서→동), obu2(남→북)
- obu/obu.py: TraCI로 차량 상태 읽기 → BSM 생성 → UDP 전송. SUMO에 클라이언트 2개로 동시 접속
- common/j2735.py: BSM 생성(make_bsm)과 해석(decode). 단위 변환: 위경도 1e-7도, 속도 0.02 m/s, 방향 0.0125도
- scripts/build_j2735.sh: SAE J2735ASN_202409(43개 파일)를 pycrate로 컴파일 → common/j2735_gen.py

## SAE J2735 파일
- SAE Mobilus에서 J2735ASN_202409 무료 다운로드 (계정 필요)
- 라이선스 때문에 asn/ 와 common/j2735_gen.py 는 .gitignore로 제외. 각자 받아 build_j2735.sh 실행
- 일부 파일이 UTF-8이 아니라 스크립트가 변환 후 컴파일
- 검증: V2X-Hub 샘플 BSM을 디코딩 → 1단계 로그와 같은 값, 재인코딩 시 원본 바이트와 일치

## 실행
    sumo-gui -c sumo/intersection.sumocfg --remote-port 8813 --num-clients 2 --start
    python3 obu/obu.py --vehicle obu1 --order 1
    python3 obu/obu.py --vehicle obu2 --order 2

## 겪은 문제
- MsgCount 범위: J2735-Common은 0..127 (AddGrpB의 0..255와 다름) → 0..127 순환으로 수정
- VS Code에서 새 파일을 만들고 저장하지 않아 0바이트 파일이 생김, 파일 이름에 탭 문자가 들어감 → 터미널로 확인 후 수정
