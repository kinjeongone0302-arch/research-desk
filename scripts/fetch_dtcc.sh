#!/bin/bash
# DTCC 공개 스왑 체결 공시(Public Price Dissemination) 수집.
# SEC = 단일물 CDS(single-name), CFTC = 지수 CDS. 둘 다 인증 불필요.
# 이미 받은 날짜는 건너뛴다. 주말/휴일은 404 → 0바이트 파일은 지운다.
set -u
RAW="$(cd "$(dirname "$0")/.." && pwd)/cds/raw"
mkdir -p "$RAW"
get() {
  local venue=$1 d=$2 low
  low=$(echo "$venue" | tr 'A-Z' 'a-z')
  local out="$RAW/${venue}_${d}.zip"
  [ -s "$out" ] && return 0
  curl -sf --max-time 90 --retry 2 \
    -o "$out" "https://pddata.dtcc.com/ppd/api/report/cumulative/${low}/${venue}_CUMULATIVE_CREDITS_${d}.zip" \
    || rm -f "$out"
}
export -f get; export RAW
python3 "$(dirname "$0")/dates.py" "${1:-2025-01-01}" \
  | xargs -P 6 -I{} bash -c 'get SEC {}; get CFTC {}'
find "$RAW" -size -1k -delete
ls "$RAW" | wc -l
