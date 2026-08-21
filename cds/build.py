"""DTCC 공개 공시 → 대시보드용 CDS 데이터셋.

산출: site/data/cds.json
  - 한국 국가 CDS 5Y 일별 시계열 + 만기별 커브
  - 아시아·신흥국 국가 CDS 비교
  - 국내 기업·정책금융 단일물 체결 내역
  - 지수 CDS(CDX/iTraxx) — 지수물은 스프레드가 공시에 직접 들어와 역산이 필요 없다
"""
import datetime as dt
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parse
from price import branches, _solve

OUT = Path(__file__).resolve().parents[1] / "site" / "data" / "cds.json"

# 표시명 → 공시 표기 정규식. DTCC 는 대소문자·표기가 제각각이라 정규식으로 묶는다.
SOVEREIGN = {
    "한국":       r"republic of korea",
    "중국":       r"people'?s republic of china",
    "일본":       r"^japan$",
    "인도네시아": r"republic of indonesia",
    "필리핀":     r"republic of the philippines",
    "말레이시아": r"^malaysia$",
    "베트남":     r"socialist republic of viet\s?nam",
    "인도":       r"republic of india",
    "태국":       r"kingdom of thailand",
    "브라질":     r"federative republic of brazil",
    "멕시코":     r"united mexican states",
    "튀르키예":   r"republic of t(ur|ür)key|republic of turkiye",
    "남아공":     r"republic of south africa",
    "사우디":     r"kingdom of saudi arabia",
}

KOREA_CREDIT = {
    "SK하이닉스":   r"sk\s?hynix",
    "LG화학":       r"lg\s?chem",
    "POSCO홀딩스":  r"posco",
    "산업은행":     r"korea development bank",
    "수출입은행":   r"export-?import bank of korea",
    "LH":           r"korea land\s?&?\s?housing",
    "한국전력":     r"korea electric power",
    "가스공사":     r"korea gas",
    "현대차":       r"hyundai motor",
    "기아":         r"^kia\b",
    "삼성전자":     r"samsung electronics",
    "신한은행":     r"shinhan bank",
    "국민은행":     r"kookmin bank",
    "우리은행":     r"woori bank",
    "하나은행":     r"hana bank",
}

# AI 캐펙스를 부채로 조달하는 크레딧. Oracle 은 이 데이터셋 전체에서 체결이 가장 많은
# 기업 단일물이다(최근 130영업일 995건) — AI 투자 사이클의 신용위험 게이지로 쓰인다.
AI_CREDIT = {
    "Oracle":      r"^oracle (corp|cop)|^orcl cds",
    "CoreWeave":   r"^coreweave[;,. ]*(inc|corp)?\.?$|^coreweave cds",
    "SoftBank":    r"^softbank( group)?( corp)?\.?$",
    "Meta":        r"^meta platforms",
    "Microsoft":   r"^microsoft( corp)?",
    "Alphabet":    r"^alphabet inc",
    "Amazon":      r"^amazon\.com",
    "Broadcom":    r"^broadcom inc",
    "NVIDIA":      r"^nvidia corp",
    "Dell":        r"^dell (inc|technologies)|^dell cds",
    "Intel":       r"^intel corp|^intel cds",
    "Vistra":      r"^vistra operations",
    "NRG":         r"^nrg energy|^nrg cds",
    "Constellation": r"^constellation energy generation",
}

INDEX = {
    "CDX IG":            r"^cdx\.na\.ig",
    "CDX HY":            r"^cdx\.na\.hy",
    "CDX EM":            r"^cdx\.em",
    "iTraxx Europe":     r"^itraxx europe$",
    "iTraxx Crossover":  r"^itraxx europe crossover",
    "iTraxx Asia ex-JP": r"^itraxx asia ex-?japan",
    "iTraxx Japan":      r"^itraxx japan",
}

# CDX.NA.HY 는 스프레드가 아니라 가격(100 기준)으로 호가된다. 공시는 그 값을 그대로
# Spread 칸에 넣어 108bp 처럼 보이지만 실제로는 가격 107.9 다 — 표기 코드로는 구분되지
# 않아(IG 도 같은 코드) 지수별 관행으로 지정한다. 쿠폰 500bp 로 되돌리면 300bp대가 나온다.
PRICE_QUOTED = {"CDX HY"}
MIN_INDEX_TRADES = 20

TENOR_BUCKETS = [(0.75, 1.5, "1Y"), (2.5, 3.5, "3Y"), (3.5, 4.5, "4Y"),
                 (4.5, 5.6, "5Y"), (6.5, 8.0, "7Y"), (8.5, 11.0, "10Y"),
                 (13.0, 17.0, "15Y"), (18.0, 32.0, "20Y+")]


def bucket(tenor):
    for lo, hi, name in TENOR_BUCKETS:
        if lo <= tenor < hi:
            return name
    return None


def compile_map(m):
    return [(k, re.compile(v, re.I)) for k, v in m.items()]


def match(name, compiled):
    for label, rx in compiled:
        if rx.search(name):
            return label
    return None


# 업프론트 부호가 공시되지 않아 해가 둘 붙는다(price.branches 참고).
# 1순위: 같은 종목에 스프레드가 직접 공시된 체결이 있으면 그 중앙값에 가까운 쪽을 고른다.
# 2순위: 한쪽에서만 풀리는 거래의 비중. 일본·멕시코처럼 1건짜리 잡음이 섞이므로 비율로 본다.
HIGH_BRANCH_SHARE = 0.03
MIN_QUOTES_FOR_BRANCH = 5


def collect():
    """공시 zip 전체를 훑어 관심 대상만 뽑는다. 단일물은 역산, 지수물은 공시 스프레드 사용."""
    sov, corp = compile_map(SOVEREIGN), compile_map(KOREA_CREDIT)
    ai, idx = compile_map(AI_CREDIT), compile_map(INDEX)
    single, index_rows = [], []
    tally = defaultdict(lambda: [0, 0])       # 종목 → [low 에서만 풀림, high 에서만 풀림]
    quotes = defaultdict(list)                # 종목 → 직접 공시된 5Y 스프레드
    seen = set()

    days = parse.all_days()
    for n, (venue, day) in enumerate(days):
        if n % 200 == 0:
            print(f"  파싱 {n}/{len(days)}", file=sys.stderr, flush=True)
        for t in parse.trades(venue, day):
            exec_d = dt.date.fromisoformat(t["exec"])
            if not 0 <= (day - exec_d).days <= 5:
                continue                      # 과거 계약 정정(MODI) 은 시세가 아니다

            if venue == "CFTC":
                label = match(t["index"], idx)
                if not label or t["spread"] is None or not t["tenor"]:
                    continue
                if ("I", t["id"]) in seen:
                    continue
                seen.add(("I", t["id"]))
                # 가격 호가 지수는 여기서 변환하지 않는다. 체결 건마다 풀면 수십만 번이라
                # 느리고, 어차피 화면에 쓰는 건 일별 중앙값이다 — 집계 후 한 번만 되돌린다.
                index_rows.append({"name": label, "date": t["exec"], "tenor": t["tenor"],
                                   "bucket": bucket(t["tenor"]), "bp": t["spread"] * 1e4,
                                   "maturity": t["maturity"], "coupon": t["coupon"] or 0.05,
                                   "notional": t["notional"]})
                continue

            if "SN" not in t["fisn"]:
                continue
            label = match(t["entity"], sov) or match(t["entity"], corp) or match(t["entity"], ai)
            if not label:
                continue
            if not (t["upfront"] and t["notional"] and t["notional"] >= 1e5):
                continue
            coupon = t["coupon"] or 0.01
            if coupon not in (0.01, 0.05):
                continue                      # 표준 쿠폰(IG 100bp / HY 500bp)만. 그 외는 극소수
            key = ("S", t["exec"], t["maturity"], t["upfront"], t["notional"], t["spread"])
            if key in seen:
                continue
            seen.add(key)

            kind = ("sov" if label in SOVEREIGN
                    else "kr" if label in KOREA_CREDIT else "ai")

            # 단일물의 약 4분의 1은 딜러 호가가 스프레드 칸에 그대로 실린다. 있으면 역산하지 않는다.
            if t["spread"] is not None:
                single.append({"name": label, "kind": kind, "date": t["exec"],
                               "maturity": t["maturity"], "tenor": t["tenor"],
                               "bucket": bucket(t["tenor"]), "src": "quoted",
                               "_lo": t["spread"] * 1e4, "_hi": t["spread"] * 1e4,
                               "notional": t["notional"], "capped": t["capped"]})
                if 4.5 <= t["tenor"] <= 5.6:
                    quotes[label].append(t["spread"] * 1e4)
                continue

            lo, hi = branches(exec_d, dt.date.fromisoformat(t["maturity"]),
                              t["upfront"] / t["notional"], coupon)
            ok_lo, ok_hi = lo == lo, hi == hi
            if not (ok_lo or ok_hi):
                continue
            if ok_lo != ok_hi:
                tally[label][0 if ok_lo else 1] += 1
            single.append({"name": label, "kind": kind, "coupon": coupon, "src": "derived",
                           "date": t["exec"], "maturity": t["maturity"], "tenor": t["tenor"],
                           "bucket": bucket(t["tenor"]),
                           "_lo": lo * 1e4 if ok_lo else None,
                           "_hi": hi * 1e4 if ok_hi else None,
                           "notional": t["notional"], "capped": t["capped"]})

    sides = {}
    for label in {r["name"] for r in single}:
        q = quotes.get(label, [])
        if len(q) >= MIN_QUOTES_FOR_BRANCH:
            ref = statistics.median(q)
            cand = [r for r in single if r["name"] == label and r.get("src") == "derived"
                    and r["bucket"] == "5Y" and r["_lo"] and r["_hi"]]
            if cand:
                lo_err = statistics.median(abs(r["_lo"] - ref) for r in cand)
                hi_err = statistics.median(abs(r["_hi"] - ref) for r in cand)
                sides[label] = "high" if hi_err < lo_err else "low"
                continue
        only_lo, only_hi = tally[label]
        n = sum(1 for r in single if r["name"] == label)
        sides[label] = "high" if n and only_hi / n > HIGH_BRANCH_SHARE else "low"

    return single, index_rows, sides


def resolve(rows, seed="low"):
    """날짜순으로 훑으며 업프론트 부호(분기)를 하루 단위로 정하고 5Y 시계열을 만든다.

    종목마다 분기를 하나로 고정하면 안 된다. 오라클처럼 표준쿠폰(100bp) 선을 기간 중에
    넘는 크레딧이 있고, 그런 종목이야말로 보고 싶은 대상이다. 2025년 50bp대에서
    2026년 200bp대로 갔는데 한쪽으로 고정하면 절반이 통째로 틀린다.

    기준점은 두 가지다 — 그날 딜러 호가가 공시됐으면 그 값(약 4분의 1의 날),
    없으면 직전에 확정된 값. 두 해 중 기준점에 가까운 쪽을 택한다.
    """
    by_day = defaultdict(list)
    for r in rows:
        by_day[r["date"]].append(r)

    days = sorted(by_day)

    def medians(rs):
        q = [r["_lo"] for r in rs if r.get("src") == "quoted" and r["bucket"] == "5Y"]
        dv = [r for r in rs if r.get("src") == "derived" and r["bucket"] == "5Y"]
        lo = [r["_lo"] for r in dv if r["_lo"] is not None]
        hi = [r["_hi"] for r in dv if r["_hi"] is not None]
        return (statistics.median(q) if q else None,
                statistics.median(lo) if lo else None,
                statistics.median(hi) if hi else None)

    # 호가가 실린 날을 길잡이로 삼는다. 직전 값만 보고 따라가면 한 번 잘못 잡은 분기를
    # 계속 끌고 가므로, 호가와 호가 사이 구간은 양쪽 끝을 이어 만든 값에 붙인다.
    qs = [(d, medians(by_day[d])[0]) for d in days]
    qs = [(d, v) for d, v in qs if v is not None]

    def waypoint(d):
        if not qs:
            return None
        prev = [x for x in qs if x[0] <= d]
        nxt = [x for x in qs if x[0] > d]
        if prev and nxt:
            (d0, v0), (d1, v1) = prev[-1], nxt[0]
            t0 = dt.date.fromisoformat(d0); t1 = dt.date.fromisoformat(d1)
            w = (dt.date.fromisoformat(d) - t0).days / max((t1 - t0).days, 1)
            return v0 + w * (v1 - v0)
        return (prev[-1][1] if prev else nxt[0][1])

    series, side_of_day, cands = {}, {}, {}
    last = None
    for d in days:
        rs = by_day[d]
        quoted, lo, hi = medians(rs)
        anchor = quoted if quoted is not None else (waypoint(d) or last)
        if anchor is None:
            side = seed
        else:
            cand = {}
            if lo is not None:
                cand["low"] = abs(lo - anchor)
            if hi is not None:
                cand["high"] = abs(hi - anchor)
            side = min(cand, key=cand.get) if cand else (side_of_day.get(d) or seed)
        side_of_day[d] = side

        val, src = (quoted, "quoted") if quoted is not None else \
                   ((lo if side == "low" else hi), "derived")
        if val is None:
            # 5Y 체결이 없는 날은 앞뒤 만기로 보간한다
            pts = [(r["tenor"], (r["_lo"] if side == "low" else r["_hi"]) if r.get("src") == "derived" else r["_lo"])
                   for r in rs]
            pts = [(t, v) for t, v in pts if v is not None]
            a = [p for p in pts if p[0] < 4.5]
            b = [p for p in pts if p[0] >= 5.6]
            if a and b:
                a, b = max(a), min(b)
                w = (5.0 - a[0]) / (b[0] - a[0])
                val, src = a[1] + w * (b[1] - a[1]), "interp"
        if val is None or not 0.5 < val < 3000:
            continue
        series[d] = (round(val, 2), src)
        cands[d] = (quoted, lo, hi)
        last = val

    _smooth(series, cands, side_of_day)
    return series, side_of_day


def _smooth(series, cands, side_of_day, rounds=2):
    """이웃값으로 한 번 더 훑는다.

    호가가 거의 없는 종목은 기준점 사슬이 약해서, 체결 한두 건짜리 날에 반대쪽 해가
    잘못 뽑히면 그대로 남는다(460bp 다음날 1bp 같은 값). 앞뒤 관측의 중앙값과 견줘
    반대쪽 해가 더 맞으면 바꾸고, 그래도 동떨어지면 그날은 버린다.
    """
    for _ in range(rounds):
        days = sorted(series)
        for i, d in enumerate(days):
            if d not in series or series[d][1] == "quoted":
                continue
            near = [series[x][0] for x in days[max(0, i - 4):i + 5]
                    if x != d and x in series
                    and abs((dt.date.fromisoformat(x) - dt.date.fromisoformat(d)).days) <= 30]
            if len(near) < 3:
                continue
            ref = statistics.median(near)
            _, lo, hi = cands.get(d, (None, None, None))
            opts = [(abs(v - ref), v, side) for v, side in ((lo, "low"), (hi, "high")) if v is not None]
            if not opts:
                continue
            err, val, side = min(opts)
            if err > max(0.6 * ref, 80):
                del series[d]                     # 어느 쪽으로도 설명이 안 되는 날
                continue
            side_of_day[d] = side
            series[d] = (round(val, 2), series[d][1])


def apply_side(rows, side_of_day, seed="low"):
    """확정된 분기로 각 체결의 스프레드를 정한다 (커브·최근체결 표시에 쓴다)."""
    out = []
    for r in rows:
        side = side_of_day.get(r["date"], seed)
        bp = r["_lo"] if (r.get("src") == "quoted" or side == "low") else r["_hi"]
        if bp is None or not 0.5 < bp < 3000:
            continue
        out.append({**{k: v for k, v in r.items() if not k.startswith("_")},
                    "bp": round(bp, 2)})
    return out


def curve(rows, days=45):
    """최근 N일 체결로 만기별 커브 스냅샷."""
    if not rows:
        return []
    cut = (dt.date.fromisoformat(max(r["date"] for r in rows)) - dt.timedelta(days=days)).isoformat()
    by_b = defaultdict(list)
    for r in rows:
        if r["date"] >= cut and r["bucket"]:
            by_b[r["bucket"]].append(r["bp"])
    order = [n for _, _, n in TENOR_BUCKETS]
    return [{"tenor": b, "bp": round(statistics.median(v), 2), "n": len(v)}
            for b in order if (v := by_b.get(b))]


CACHE = Path(__file__).resolve().parent / "trades_cache.json"


def main():
    reuse = "--reuse" in sys.argv and CACHE.exists()
    if reuse:
        c = json.loads(CACHE.read_text())
        single, index_rows, sides = c["single"], c["index"], c["sides"]
        print(f"캐시 재사용 — 단일물 {len(single)}건", file=sys.stderr, flush=True)
    else:
        single, index_rows, sides = collect()
        CACHE.write_text(json.dumps({"single": single, "index": index_rows, "sides": sides},
                                    separators=(",", ":")))
    print(f"단일물 {len(single)}건 · 지수물 {len(index_rows)}건", file=sys.stderr, flush=True)

    by_name = defaultdict(list)
    for r in single:
        by_name[r["name"]].append(r)

    def pack(name, rs, curve_days):
        series, side_of_day = resolve(rs, sides.get(name, "low"))
        trades = apply_side(rs, side_of_day, sides.get(name, "low"))
        crossed = len(set(side_of_day.values())) > 1
        return {
            "trades": len(trades),
            "series": [{"d": d, "bp": v, "src": s} for d, (v, s) in sorted(series.items())],
            "curve": curve(trades, curve_days),
            "branch": ("mixed" if crossed else
                       (list(side_of_day.values())[-1] if side_of_day else "low")),
            "quoted": sum(1 for t in trades if t.get("src") == "quoted"),
            "recent": sorted(trades, key=lambda r: r["date"], reverse=True)[:40],
            "last": max(series) if series else None,
            "last_bp": series[max(series)][0] if series else None,
        }

    sovereigns = {}
    for name in SOVEREIGN:
        rs = by_name.get(name, [])
        if rs:
            d = pack(name, rs, 45)
            d.pop("recent")
            sovereigns[name] = d

    corps = {}
    for name in KOREA_CREDIT:
        rs = by_name.get(name, [])
        if rs:
            corps[name] = pack(name, rs, 400)

    ai_out = {}
    for name in AI_CREDIT:
        rs = by_name.get(name, [])
        if rs:
            ai_out[name] = pack(name, rs, 90)

    idx = defaultdict(list)
    for r in index_rows:
        idx[r["name"]].append(r)
    indices = {}
    for name, rs in idx.items():
        five = [r for r in rs if r["bucket"] == "5Y"]
        by_day = defaultdict(list)
        for r in (five or rs):
            by_day[r["date"]].append(r["bp"])
        if name in PRICE_QUOTED:
            # 가격(100 기준) → par spread. 100 초과면 매수자가 업프론트를 받는 쪽이다.
            mats = {r["date"]: (r["maturity"], r["coupon"]) for r in (five or rs)}
            ser = []
            for d, v in sorted(by_day.items()):
                mat, cpn = mats[d]
                x = _solve(dt.date.fromisoformat(d), dt.date.fromisoformat(mat),
                           (100.0 - statistics.median(v)) / 100.0, cpn)
                if x == x:
                    ser.append({"d": d, "bp": round(x * 1e4, 2)})
        else:
            ser = [{"d": d, "bp": round(statistics.median(v), 2)} for d, v in sorted(by_day.items())]
        if len(rs) < MIN_INDEX_TRADES:
            continue                          # 체결 한두 건짜리 지수는 시세로 보기 어렵다
        indices[name] = {"trades": len(rs), "series": ser,
                         "last_bp": ser[-1]["bp"] if ser else None}

    doc = {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": "DTCC Public Price Dissemination (SEC/CFTC swap data repository)",
        "method": ("표준쿠폰 100bp 계약의 업프론트 현금을 ISDA 표준모형(회수율 40%)으로 역산해 "
                   "par spread 산출. 노셔널은 $5m 초과분이 마스킹돼 하한값을 쓴다."),
        "coverage": {"days": len(parse.all_days()) // 2,
                     "from": min(r["date"] for r in single) if single else None,
                     "to": max(r["date"] for r in single) if single else None},
        "sovereigns": sovereigns, "corps": corps, "ai": ai_out, "indices": indices,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
    print(f"→ {OUT}  ({OUT.stat().st_size/1024:.0f} KB)", file=sys.stderr)
    for n, v in list(sovereigns.items()) + list(ai_out.items()):
        print(f"  {n:12} {v['trades']:5d}건 (호가 {v['quoted']:4d})  5Y {v['last_bp']}bp"
              f"  [{v['branch']}]  ({v['last']})", file=sys.stderr)


if __name__ == "__main__":
    main()
