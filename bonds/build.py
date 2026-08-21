"""회사채 스프레드 데이터셋 → site/data/bonds.json"""
import datetime as dt
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import fetch

OUT = BASE.parent / "site" / "data" / "bonds.json"
KEEP_FROM = "2025-01-01"          # CDS 수집 범위와 맞춘다
TENORS = ["1 Yr", "2 Yr", "3 Yr", "5 Yr", "7 Yr", "10 Yr", "20 Yr", "30 Yr"]


def main():
    oas = {}
    for label, sid in fetch.OAS.items():
        ser = [{"d": d, "bp": v} for d, v in fetch.oas(label, sid).items() if d >= KEEP_FROM]
        if ser:
            oas[label] = {"series": ser, "last_bp": ser[-1]["bp"], "last": ser[-1]["d"],
                          "fred": sid}

    years = range(int(KEEP_FROM[:4]), dt.date.today().year + 1)
    ust = fetch.treasury(years)
    curve = [{"d": d, **{t.replace(" Yr", "Y").replace(" ", ""): v[t]
                         for t in TENORS if t in v}}
             for d, v in ust.items() if d >= KEEP_FROM]

    doc = {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": "ICE BofA 지수 OAS (FRED) · 미 재무부 일별 금리곡선",
        "note": ("OAS 는 같은 만기 국채 대비 초과수익률이라 CDS 와 정의가 다르다. "
                 "레벨을 맞대지 말고 같은 지표끼리만 비교할 것."),
        "oas": oas,
        "treasury": curve,
        "trace": None,                # 개별 회사채 체결 — FINRA 계정 필요
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
    print(f"→ {OUT}  ({OUT.stat().st_size/1024:.0f} KB)")
    for k, v in oas.items():
        print(f"  {k:8} {v['last_bp']:7.1f}bp  ({v['last']})")
    print(f"  국채곡선 {len(curve)}일")


if __name__ == "__main__":
    main()
