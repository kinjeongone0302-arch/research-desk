"""수집 캐시 → 대시보드용 기업 데이터.

산출:
  site/data/fin_index.json        전 종목 검색 인덱스 (국내 + 미국)
  site/data/fin/KR/{종목코드}.json  종목별 개요 + 재무
  site/data/fin/US/{티커}.json
종목별로 파일을 쪼개는 건 정적 사이트에서 필요한 하나만 받아가게 하기 위해서다.
"""
import json
import re
import sys
import datetime as dt
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import dart
import edgar
import fetch_us

SITE = BASE.parent / "site" / "data"

# DART 주요계정 이름 → 짧은 키
KR_ACCT = {
    "매출액": "rev", "영업이익": "op", "법인세차감전 순이익": "pre",
    "당기순이익(손실)": "net", "총포괄손익": "ci",
    "자산총계": "assets", "부채총계": "liab", "자본총계": "equity",
    "유동자산": "ca", "비유동자산": "nca", "유동부채": "cl", "비유동부채": "ncl",
    "자본금": "cap", "이익잉여금": "re",
}


def amt(s):
    s = (s or "").replace(",", "").strip()
    if not s or s == "-":
        return None
    try:
        return int(s)
    except ValueError:
        return None


def year_of(dt_str):
    """'2025.01.01 ~ 2025.12.31' / '2025.12.31 현재' → 2025"""
    m = re.findall(r"(\d{4})\.\d{2}\.\d{2}", dt_str or "")
    return int(m[-1]) if m else None


QKEY = {"Q1": 1, "H1": 2, "Q3": 3}


def qsort(label):
    """'2026H1' → (2026, 2). 문자열 정렬로는 반기와 3분기 순서가 뒤집힌다."""
    return (int(label[:4]), QKEY.get(label[4:], 9))


def build_kr():
    m = dart.corp_map()
    corp2stock = {v[0]: k for k, v in m.items()}

    # (종목, 기간라벨) → {계정: 값}
    annual = defaultdict(dict)
    quarter = defaultdict(dict)

    for f in sorted((BASE / "cache" / "kr_acct").glob("*.json")):
        year, rep, _ = f.stem.split("_")
        try:
            rows = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        for r in rows:
            if r.get("fs_div") != "CFS":          # 연결 우선. 없는 회사는 아래에서 별도로 채운다
                continue
            key = KR_ACCT.get(r.get("account_nm"))
            stock = corp2stock.get(r.get("corp_code"))
            if not key or not stock:
                continue
            if rep == "11011":
                # 사업보고서 한 건에 당기·전기·전전기가 함께 온다
                for pre, dtk in (("thstrm", "thstrm_dt"), ("frmtrm", "frmtrm_dt"),
                                 ("bfefrmtrm", "bfefrmtrm_dt")):
                    y = year_of(r.get(dtk))
                    v = amt(r.get(pre + "_amount"))
                    if y and v is not None:
                        annual[(stock, str(y))].setdefault(key, v)
            else:
                label = f"{year}{dart.LABELS[rep]}"
                v = amt(r.get("thstrm_amount"))
                if v is not None:
                    quarter[(stock, label)].setdefault(key, v)

    # 개요는 종목별 호출이라 한 회차에 다 못 받는다. 캐시가 진행률이고 실행할 때마다 채워진다.
    size = {s: annual.get((s, "2025"), {}).get("rev") or 0 for s in {k[0] for k in annual}}
    profs = (dart.profiles(m, order=size) if dart.alive()
             else dart.profiles(m, budget=0))

    out = BASE.parent / "site" / "data" / "fin" / "KR"
    out.mkdir(parents=True, exist_ok=True)

    index = []
    for stock, (corp, name) in m.items():
        a = sorted((p for (s, p) in annual if s == stock), reverse=True)[:7]
        q = sorted((p for (s, p) in quarter if s == stock), key=qsort, reverse=True)[:8]
        if not a and not q:
            continue
        p = profs.get(stock, {})
        doc = {
            "market": "KR", "code": stock, "name": p.get("stock_name") or name,
            "corp_code": corp,
            "profile": {k: p.get(k) for k in
                        ("corp_name", "corp_name_eng", "ceo_nm", "est_dt", "adres",
                         "hm_url", "ir_url", "induty_code", "acc_mt", "corp_cls")},
            "annual": [{"period": pp, **annual[(stock, pp)]} for pp in sorted(a)],
            "quarter": [{"period": pp, **quarter[(stock, pp)]} for pp in sorted(q, key=qsort)],
        }
        (out / f"{stock}.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
        last = doc["annual"][-1] if doc["annual"] else {}
        index.append({"t": stock, "n": doc["name"], "m": "KR",
                      "e": (p.get("corp_name_eng") or "")[:40],
                      "rev": last.get("rev")})
    return index


def build_us():
    tk = edgar.tickers()
    data = edgar.collect(fetch_us.ANNUAL, fetch_us.QUARTER, fetch_us.INSTANT)

    by_cik = defaultdict(dict)
    for (cik, period), vals in data.items():
        by_cik[cik][period] = vals

    out = BASE.parent / "site" / "data" / "fin" / "US"
    out.mkdir(parents=True, exist_ok=True)

    index = []
    seen_us = set()
    for cik, periods in by_cik.items():
        meta = tk.get(cik)
        if not meta:
            continue                            # 티커가 없는 신고인(펀드·SPV 등)은 제외
        name = meta["name"] or next((v.get("name") for v in periods.values() if v.get("name")), "")

        def merge(dur, inst):
            """기간 손익 + 같은 시점 잔액을 한 줄로 합친다."""
            row = {"period": dur}
            row.update({k: v for k, v in periods.get(dur, {}).items() if k != "name"})
            row.update({k: v for k, v in periods.get(inst, {}).items() if k != "name"})
            return row if len(row) > 1 else None

        annual = [r for r in (merge(p, p + "Q4I") for p in fetch_us.ANNUAL) if r]
        quarter = [r for r in (merge(p, p + "I") for p in fetch_us.QUARTER) if r]
        if not annual and not quarter:
            continue
        f = out / f"{meta['ticker'].upper()}.json"
        # 보완분(companyfacts 기반)이 더 길면 덮어쓰지 않는다
        keep = None
        if f.exists():
            try:
                keep = json.loads(f.read_text())
            except json.JSONDecodeError:
                keep = None
        if not (keep and len(keep.get("annual", [])) > len(annual)):
            keep = {"market": "US", "ticker": meta["ticker"].upper(), "name": name, "cik": cik,
                    "exchange": meta.get("exchange"), "unit": "USD",
                    "annual": annual, "quarter": quarter}
            # 같은 CIK 의 다른 티커(우선주 등)로도 찾아지게 별칭 파일을 함께 쓴다
            for t in meta.get("tickers") or [meta["ticker"]]:
                (out / f"{t.upper()}.json").write_text(
                    json.dumps({**keep, "ticker": t.upper()}, ensure_ascii=False,
                               separators=(",", ":")))
        seen_us.add(meta["ticker"].upper())

    # frames 에 없지만 보완으로 만들어진 파일(외국 발행사 등)도 인덱스에 넣는다
    for f in sorted(out.glob("*.json")):
        t = f.stem.upper()
        try:
            doc = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        a = doc.get("annual") or []
        index.append({"t": t, "n": doc.get("name") or t, "m": "US",
                      "e": doc.get("exchange") or "", "u": doc.get("unit") or "USD",
                      "rev": (a[-1] if a else {}).get("revenue")})
    return index


def main():
    idx = []
    idx += build_kr()
    idx += build_us()
    idx.sort(key=lambda x: -(x.get("rev") or 0))
    SITE.mkdir(parents=True, exist_ok=True)
    (SITE / "fin_index.json").write_text(json.dumps(
        {"built_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
         "count": len(idx), "rows": idx}, ensure_ascii=False, separators=(",", ":")))
    kr = sum(1 for r in idx if r["m"] == "KR")
    print(f"→ fin_index.json  국내 {kr:,} · 미국 {len(idx)-kr:,} = {len(idx):,}개")


if __name__ == "__main__":
    main()
