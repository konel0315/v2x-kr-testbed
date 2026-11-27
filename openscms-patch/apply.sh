#!/usr/bin/env bash
# OpenSCMS에 V2X 시험환경용 수정을 적용한다.
#  - 응용인증서에 단말이 요청한 PSID(appPermissions)를 넣는다 (ACA)
#  - RA가 장치 종류(OBU/RSU)별로 허용된 PSID만 받아 준다 (400-30 disallowed appPermissions)
#  - NonButterfly 응용인증서 유효기간을 '지금부터 1년'으로 한다
#  - (V2P·V2N) 휴대 단말(OBU 종류)에 PSM 0x27, 인프라(RSU 종류)에 TIM 0x8003 권한을 허용한다
# 사용법: bash openscms-patch/apply.sh [OpenSCMS 폴더, 기본 ~/openscms/OpenSCMS]
# 되돌리기: bash openscms-patch/revert.sh
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
OSC="${1:-$HOME/openscms/OpenSCMS}"
BR="$OSC/oscms_bridge/oscms-codecs-bridge"

apply() {   # $1 폴더, $2 패치, $3 적용됐는지 알아보는 파일, $4 그 파일에 들어 있는 글자
  if grep -q -- "$4" "$1/$3" 2>/dev/null; then
    echo "이미 적용됨: $(basename "$2")"
  else
    git -C "$1" apply --check "$2"
    git -C "$1" apply "$2"
    echo "적용 완료: $(basename "$2")"
  fi
}
apply "$OSC" "$HERE/openscms.patch"             ra/src/ra_endpoint/authorization_cert.rs check_psid_policy
apply "$BR"  "$HERE/oscms-codecs-bridge.patch"  src/certificate_util.c                   app_psids_count
apply "$OSC" "$HERE/psid-policy-v2p-v2n.patch"  deployment/values.yaml                   '0x20,0x27'
echo
echo "이제 OpenSCMS를 다시 올리세요:"
echo "  cd $OSC && skaffold run && kubectl rollout restart deployment/ra-deployment"
