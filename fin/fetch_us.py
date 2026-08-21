"""EDGAR 원본 수집 (캐시 채우기)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import edgar

ANNUAL = [f"CY{y}" for y in range(2021, 2026)]
QUARTER = [f"CY{y}Q{q}" for y in (2025, 2026) for q in (1, 2, 3, 4)][:6]
INSTANT = [f"CY{y}Q4I" for y in range(2021, 2026)] + ["CY2026Q1I", "CY2026Q2I"]

if __name__ == "__main__":
    t = edgar.tickers()
    print(f"티커 {len(t)}개", flush=True)
    data = edgar.collect(ANNUAL, QUARTER, INSTANT)
    ciks = {c for c, _ in data}
    print(f"수집 완료 — {len(data):,}개 (기업, 기간) 조합 · 기업 {len(ciks):,}개", flush=True)
    print(f"티커 매칭 {len({c for c in ciks if c in t}):,}개", flush=True)
