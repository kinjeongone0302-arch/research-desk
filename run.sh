#!/bin/bash
# 전체 갱신. 각 단계는 캐시 기반이라 중간에 끊겨도 다음 실행에서 이어받는다.
# 인자로 DTCC 수집 시작일을 줄 수 있다(기본 최근 14일). 전체 재수집은 ./run.sh 2025-01-01
set -eu
cd "$(dirname "$0")"
FROM="${1:-$(python3 -c 'import datetime as d;print(d.date.today()-d.timedelta(days=14))')}"

echo "[1/8] DTCC 스왑 공시 수집 ($FROM ~)"
./scripts/fetch_dtcc.sh "$FROM"

echo "[2/8] CDS 역산"
python3 cds/build.py

echo "[3/8] 회사채 스프레드 (FRED · 미 재무부)"
python3 bonds/build.py

echo "[4/8] 수주잔고"
python3 scripts/build_backlog.py

echo "[5/8] 재무 원본 — DART"
# 다중회사 API 로 전 종목 재무를 40회 남짓에 받는다.
python3 fin/fetch_kr.py || echo "  DART 수집 실패 — 다음 실행에서 이어받음"
# 개요는 종목당 1회 호출이라 한 번에 다 받으면 IP 가 막힌다. 매출 큰 순으로 나눠 받는다.
python3 fin/fill_profiles.py 6 || true

echo "[6/8] 재무 원본 — EDGAR"
python3 fin/fetch_us.py

echo "[7/8] 채널 아카이브"
~/report-bot/venv/bin/python channel/fetch.py 90 || echo "  텔레그램 수집 실패 — 세션 확인 필요"

echo "[8/8] 기업 데이터 빌드"
python3 fin/build.py
python3 fin/backfill_us.py     # frames 가 놓친 종목(비역년 결산·외국 발행사)만 개별 보완
python3 fin/build.py           # 보완분을 인덱스에 반영
python3 channel/build.py       # fin_index 가 있어야 티커 대조가 된다

echo "완료 — docs/ 가 배포본 (GitHub Pages: Settings → Pages → /docs)"
