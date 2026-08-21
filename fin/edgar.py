"""EDGAR 수집 — 미국 상장사 재무.

기업별로 companyfacts 를 받으면 한 곳당 3~5MB 라 1만 종목은 감당이 안 된다.
frames API 는 "개념 하나 × 기간 하나"를 전 종목에 대해 한 번에 주므로,
개념 12개 × 기간 10개 = 120회 호출로 전체 상장사를 덮는다.
"""
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BASE = Path(__file__).resolve().parent
CACHE = BASE / "cache"
UA = {"User-Agent": "research-desk/1.0 (kinjeongone0302@gmail.com)"}

# 같은 항목이라도 회사마다 다른 태그를 쓴다. 앞쪽 태그를 우선한다.
DURATION = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet"],
    "gross":   ["GrossProfit"],
    "op":      ["OperatingIncomeLoss"],
    "net":     ["NetIncomeLoss", "ProfitLoss"],
    "ocf":     ["NetCashProvidedByUsedInOperatingActivities",
                "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "capex":   ["PaymentsToAcquirePropertyPlantAndEquipment"],
}
INSTANT = {
    "assets": ["Assets"],
    "liab":   ["Liabilities"],
    "equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "cash":   ["CashAndCashEquivalentsAtCarryingValue"],
    "debt":   ["LongTermDebtNoncurrent", "LongTermDebt"],
}


def fetch(url, dest):
    if dest.exists():
        try:
            return json.loads(dest.read_text())
        except json.JSONDecodeError:
            pass
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read())
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(d))
            time.sleep(0.12)                  # SEC 권고 10 req/s 이내
            return d
        except Exception:
            if attempt == 2:
                return None
            time.sleep(2)


def frame(tag, period, unit="USD"):
    dest = CACHE / "us_frames" / f"{tag}_{period}.json"
    d = fetch(f"https://data.sec.gov/api/xbrl/frames/us-gaap/{tag}/{unit}/{period}.json", dest)
    return (d or {}).get("data", [])


def tickers():
    d = fetch("https://www.sec.gov/files/company_tickers.json", CACHE / "us_tickers.json") or {}
    ex = fetch("https://www.sec.gov/files/company_tickers_exchange.json",
               CACHE / "us_tickers_exchange.json") or {}
    # 한 CIK 에 티커가 여럿 달린다(ORCL / ORCL-PD 처럼 보통주와 우선주). 덮어쓰면
    # 우선주가 대표가 되어 정작 ORCL 이 사라진다 — 접미사 없는 짧은 쪽을 대표로 둔다.
    alias = {}
    for v in d.values():
        alias.setdefault(int(v["cik_str"]), {"name": v["title"], "tickers": []})
        alias[int(v["cik_str"])]["tickers"].append(v["ticker"].upper())
    exch = {}
    fields = ex.get("fields") or []
    if fields:
        ci, ti, ei = fields.index("cik"), fields.index("ticker"), fields.index("exchange")
        for row in ex.get("data", []):
            exch[(int(row[ci]), str(row[ti]).upper())] = row[ei]

    out = {}
    for cik, v in alias.items():
        ts = sorted(set(v["tickers"]), key=lambda t: ("-" in t or "." in t, len(t), t))
        out[cik] = {"ticker": ts[0], "tickers": ts, "name": v["name"],
                    "exchange": exch.get((cik, ts[0]))}
    return out


def collect(periods_annual, periods_quarter, instants, workers=4):
    """(cik, 기간) → {항목: 값}. 태그 우선순위대로 먼저 채워진 값을 유지한다."""
    jobs = []
    for item, tags in DURATION.items():
        for tag in tags:
            for p in periods_annual + periods_quarter:
                jobs.append((item, tag, p))
    for item, tags in INSTANT.items():
        for tag in tags:
            for p in instants:
                jobs.append((item, tag, p))

    out = {}
    def run(job):
        item, tag, p = job
        return item, p, frame(tag, p)

    with ThreadPoolExecutor(workers) as ex:
        for item, p, rows in ex.map(run, jobs):
            for r in rows:
                k = (r["cik"], p)
                slot = out.setdefault(k, {"name": r.get("entityName")})
                slot.setdefault(item, r.get("val"))
    return out
