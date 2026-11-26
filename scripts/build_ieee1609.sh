#!/usr/bin/env bash
# IEEE 1609.2-2022 / 1609.2.1-2022 ASN.1을 Python 모듈(common/ieee1609_gen.py)로 컴파일한다.
# ASN 파일은 OpenSCMS를 받을 때 같이 받아진 것(서브모듈)을 그대로 쓴다. OpenSCMS와 같은 판이어야 하기 때문이다.
# 사용법: bash scripts/build_ieee1609.sh [OpenSCMS 폴더, 기본 ~/openscms/OpenSCMS]
set -e
SRC="${1:-$HOME/openscms/OpenSCMS}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DST="$ROOT/asn/ieee1609"

if [ ! -d "$SRC" ]; then
  echo "OpenSCMS 폴더를 찾을 수 없습니다: $SRC"; exit 1
fi

pip install -q pycrate

rm -rf "$DST"; mkdir -p "$DST"
# 1609.2, 1609.2.1 모듈과 1609.2가 가져다 쓰는 ETSI 확장 모듈 하나
find "$SRC" -path "*/target" -prune -o -type f \( -name "Ieee1609Dot2*.asn" -o -name "EtsiTs103097ExtensionModule.asn" \) -print \
  | while read -r f; do cp "$f" "$DST/"; done
N=$(ls "$DST"/*.asn 2>/dev/null | wc -l)
if [ "$N" -lt 18 ]; then
  echo "ASN 파일이 부족합니다($N개). OpenSCMS를 --recurse-submodules로 받았는지 확인하세요."; exit 1
fi
echo "ASN 파일 ${N}개 복사"

python3 "$ROOT/scripts/fix_ieee1609_asn.py" "$DST"
pycrate_asn1compile.py -i "$DST/" -o "$ROOT/common/ieee1609_gen" 2>&1 | grep -v "WARNING" || true
test -s "$ROOT/common/ieee1609_gen.py" || { echo "컴파일 실패"; exit 1; }
echo "완료: $ROOT/common/ieee1609_gen.py"
