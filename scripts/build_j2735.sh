#!/usr/bin/env bash
# SAE J2735 ASN.1 파일을 Python 모듈(common/j2735_gen.py)로 컴파일한다.
# 사용법: bash scripts/build_j2735.sh "<ASN 파일들이 있는 폴더>"
# 예:     bash scripts/build_j2735.sh "/mnt/c/Users/konel/Downloads/J2735ASN_202409/J2735ASN_202409/V2X ASN.1 Module Collection 2024"
# 결과물과 ASN 원본은 SAE 라이선스 때문에 .gitignore로 GitHub에서 제외한다.
set -e
SRC="$1"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DST="$ROOT/asn/j2735"

if [ -z "$SRC" ] || [ ! -d "$SRC" ]; then
  echo "ASN 폴더를 찾을 수 없습니다: $SRC"; exit 1
fi

pip install -q pycrate

mkdir -p "$DST"
cp "$SRC"/*.asn "$DST"/
echo "ASN 파일 $(ls "$DST"/*.asn | wc -l)개 복사"

# 일부 파일이 UTF-8이 아니라서(Windows 인코딩) 컴파일 전에 UTF-8로 바꾼다
for f in "$DST"/*.asn; do
  python3 - "$f" <<'PY'
import sys
p = sys.argv[1]
b = open(p, "rb").read()
try:
    b.decode("utf-8")
except UnicodeDecodeError:
    open(p, "wb").write(b.decode("cp1252", errors="replace").encode("utf-8"))
    print("UTF-8로 변환:", p.rsplit("/", 1)[-1])
PY
done

pycrate_asn1compile.py -i "$DST/" -o "$ROOT/common/j2735_gen"
echo "완료: $ROOT/common/j2735_gen.py"
