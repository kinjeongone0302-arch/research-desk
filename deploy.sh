#!/bin/bash
# 갱신 → 커밋 → 푸시. GitHub Pages 가 docs/ 를 그대로 서빙한다.
# 첫 푸시는 인증이 필요하다 (README 의 '배포' 절 참고).
set -eu
cd "$(dirname "$0")"
./run.sh "$@"
git add -A
if git diff --cached --quiet; then
  echo "바뀐 게 없다"
  exit 0
fi
git commit -q -m "데이터 갱신 $(date '+%Y-%m-%d %H:%M')"
git push
echo "푸시 완료 — https://kinjeongone0302-arch.github.io/research-desk/"
