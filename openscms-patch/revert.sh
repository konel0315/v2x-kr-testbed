#!/usr/bin/env bash
# openscms-patch/apply.sh로 적용한 수정을 되돌린다.
# 사용법: bash openscms-patch/revert.sh [OpenSCMS 폴더, 기본 ~/openscms/OpenSCMS]
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
OSC="${1:-$HOME/openscms/OpenSCMS}"
BR="$OSC/oscms_bridge/oscms-codecs-bridge"
for pair in "$OSC|$HERE/openscms.patch" "$BR|$HERE/oscms-codecs-bridge.patch"; do
  d="${pair%%|*}"; p="${pair##*|}"
  if git -C "$d" apply -R --check "$p" 2>/dev/null; then
    git -C "$d" apply -R "$p"; echo "되돌림: $(basename "$p")"
  else
    echo "적용돼 있지 않음: $(basename "$p")"
  fi
done
echo "원래 OpenSCMS로 돌리려면:  cd $OSC && skaffold run"
