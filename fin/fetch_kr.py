"""DART 원본 수집 (캐시 채우기). 이미 받은 건 건너뛴다."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dart

# 사업보고서 응답에 당기·전기·전전기가 실려 2회 호출로 6년치가 나온다.
ANNUAL = [(2025, "11011"), (2022, "11011")]
QUARTER = [(2026, "11012"), (2026, "11013"),
           (2025, "11014"), (2025, "11012"), (2025, "11013")]

if __name__ == "__main__":
    m = dart.corp_map()
    print(f"상장 {len(m)}개", flush=True)
    if not dart.alive():
        print("  DART 응답 없음 — 건너뜀 (요청이 몰리면 IP 단위로 막힌다)", flush=True)
        raise SystemExit(0)
    # 재무가 먼저다. 다중회사 API 는 40회 남짓이면 전 종목이 끝나지만,
    # 개요는 종목당 1회라 한 번에 다 받으려다 차단당한다.
    corps = [v[0] for v in m.values()]
    for year, rep in ANNUAL + QUARTER:
        rows = dart.accounts(corps, year, rep)
        print(f"  {year} {dart.REPORTS[rep]:3} → {len(rows):6,}행", flush=True)
    p = dart.profiles(m)
    print(f"개요 {len(p)}개 확보 (전체 {len(m)})", flush=True)
