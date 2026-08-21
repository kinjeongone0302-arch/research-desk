"""frames 가 놓친 미국 종목 보완.

frames 는 역년(CY) 프레임이라 5월 결산 오라클 같은 회사가 빠지고, IFRS 로 신고하는
외국 발행사(ADR)는 아예 잡히지 않는다 — EDGAR frames 에 ifrs-full 은 없다.
이런 종목만 골라 companyfacts 를 개별로 받는다. 파일이 3~5MB 라 전 종목엔 못 쓰지만,
누락분 1,400여 개에는 쓸 만하다.
"""
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import edgar

OUT = BASE.parent / "site" / "data" / "fin" / "US"
FORMS = {"10-K", "20-F", "40-F"}

TAGS = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet",
                "Revenue", "RevenueFromContractsWithCustomers"],
    "gross":   ["GrossProfit"],
    "op":      ["OperatingIncomeLoss", "ProfitLossFromOperatingActivities"],
    "net":     ["NetIncomeLoss", "ProfitLoss"],
    "ocf":     ["NetCashProvidedByUsedInOperatingActivities",
                "CashFlowsFromUsedInOperatingActivities"],
    "capex":   ["PaymentsToAcquirePropertyPlantAndEquipment",
                "PurchaseOfPropertyPlantAndEquipment"],
    "assets":  ["Assets"],
    "liab":    ["Liabilities"],
    "equity":  ["StockholdersEquity", "Equity"],
    "cash":    ["CashAndCashEquivalentsAtCarryingValue", "CashAndCashEquivalents"],
    "debt":    ["LongTermDebtNoncurrent", "LongTermDebt", "NoncurrentPortionOfLongTermBorrowings"],
}


def pick_unit(facts, tags):
    """신고 통화. 외국 발행사는 TWD·CNY 등으로 낸다 — USD 만 받으면 통째로 사라진다."""
    seen = {}
    for tax in ("us-gaap", "ifrs-full"):
        for tag in tags:
            for u, rows in ((facts.get(tax, {}).get(tag) or {}).get("units") or {}).items():
                if len(u) == 3 or u.startswith("USD"):
                    seen[u] = seen.get(u, 0) + len(rows)
    if not seen:
        return None
    return "USD" if "USD" in seen else max(seen, key=seen.get)


def series(facts, tags, unit):
    """연간 신고분만 골라 {회계연도: 값}."""
    out = {}
    for tax in ("us-gaap", "ifrs-full"):
        for tag in tags:
            rows = ((facts.get(tax, {}).get(tag) or {}).get("units") or {}).get(unit) or []
            for r in rows:
                if r.get("form") not in FORMS or r.get("fp") != "FY":
                    continue
                end = r.get("end") or ""
                if len(end) >= 4:
                    out.setdefault(int(end[:4]), r.get("val"))
    return out


def one(cik, meta):
    d = edgar.fetch(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json",
                    BASE / "cache" / "us_facts" / f"{cik}.json")
    if not d:
        return False
    facts = d.get("facts") or {}
    unit = pick_unit(facts, TAGS["revenue"] + TAGS["assets"])
    if not unit:
        return False
    cols = {k: series(facts, tags, unit) for k, tags in TAGS.items()}
    years = sorted({y for v in cols.values() for y in v})[-6:]
    annual = []
    for y in years:
        row = {"period": f"FY{y}"}
        for k, v in cols.items():
            if v.get(y) is not None:
                row[k] = v[y]
        if len(row) > 1:
            annual.append(row)
    if not annual:
        return False
    doc = {"market": "US", "ticker": meta["ticker"].upper(), "name": d.get("entityName") or meta["name"],
           "cik": cik, "exchange": meta.get("exchange"), "fiscal": True, "unit": unit,
           "annual": annual, "quarter": []}
    OUT.mkdir(parents=True, exist_ok=True)
    for t in meta.get("tickers") or [meta["ticker"]]:
        (OUT / f"{t.upper()}.json").write_text(
            json.dumps({**doc, "ticker": t.upper()}, ensure_ascii=False, separators=(",", ":")))
    return True


def targets():
    tk = edgar.tickers()
    listed = {c: v for c, v in tk.items()
              if v.get("exchange") in ("Nasdaq", "NYSE", "NYSE American", "Cboe")}
    out = []
    for cik, meta in listed.items():
        f = OUT / f"{meta['ticker'].upper()}.json"
        if not f.exists():
            out.append((cik, meta))
            continue
        try:
            if len(json.loads(f.read_text()).get("annual", [])) < 3:
                out.append((cik, meta))
        except json.JSONDecodeError:
            out.append((cik, meta))
    return out


if __name__ == "__main__":
    t = targets()
    print(f"보완 대상 {len(t):,}개", flush=True)
    ok = 0
    for i, (cik, meta) in enumerate(t, 1):
        if one(cik, meta):
            ok += 1
        if i % 100 == 0:
            print(f"  {i:,}/{len(t):,} · 성공 {ok:,}", flush=True)
    print(f"완료 — {ok:,}개 보완", flush=True)
