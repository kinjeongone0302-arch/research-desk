"""본주 대비 우선주 비율 → docs/data/pref.json

비율 = 우선주 종가 / 본주 종가 × 100. 보정 없이 종가끼리 나눈다.
같은 날 둘 다 거래된 날만 쓴다(우선주는 거래정지·단일가 전환이 잦다).
"""
import datetime as dt
import json
import statistics
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import fetch

OUT = BASE.parent / "docs" / "data" / "pref.json"
START = "20200101"
MIN_DAYS = 60


def pct(v):
    return round(v, 2)


def main():
    names = fetch.listings()
    pairs = fetch.pairs(names)
    print(f"본주-우선주 {len(pairs)}쌍", file=sys.stderr, flush=True)

    close_cache = {}

    def closes(code):
        if code not in close_cache:
            close_cache[code] = fetch.closes(code, START)
        return close_cache[code]

    out = []
    for i, (bc, bn, pc, pn) in enumerate(pairs, 1):
        com, pre = closes(bc), closes(pc)
        days = sorted(set(com) & set(pre))
        if len(days) < MIN_DAYS:
            continue
        ser = [{"d": f"{d[:4]}-{d[4:6]}-{d[6:]}", "r": pct(pre[d] / com[d] * 100)}
               for d in days if com[d] > 0]
        vals = [x["r"] for x in ser]
        last = ser[-1]
        y1 = [x["r"] for x in ser if x["d"] >= (dt.date.today() - dt.timedelta(days=365)).isoformat()]
        out.append({
            "base": bc, "base_name": bn, "pref": pc, "pref_name": pn,
            "last": last["d"], "ratio": last["r"],
            "com_px": com[days[-1]], "pref_px": pre[days[-1]],
            "avg": pct(statistics.mean(vals)),
            "avg1y": pct(statistics.mean(y1)) if y1 else None,
            "min": pct(min(vals)), "max": pct(max(vals)),
            "gap": pct(last["r"] - statistics.mean(vals)),   # 평균 대비 현재 위치
            "n": len(ser),
            "series": ser[::3],                              # 화면용으로 솎는다
        })
        if i % 25 == 0:
            print(f"  {i}/{len(pairs)}", file=sys.stderr, flush=True)

    out.sort(key=lambda x: x["gap"])
    doc = {"generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
           "source": "네이버 시세 일봉 종가",
           "note": "비율 = 우선주 종가 ÷ 본주 종가 × 100. 배당 차이는 반영하지 않는다.",
           "from": START, "count": len(out), "pairs": out}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
    print(f"→ {OUT}  ({OUT.stat().st_size/1024:.0f} KB)  {len(out)}쌍", file=sys.stderr)
    print("\n평균 대비 가장 눌린 곳:", file=sys.stderr)
    for x in out[:8]:
        print(f"  {x['pref_name']:16} {x['ratio']:6.1f}%  (평균 {x['avg']:5.1f}% · {x['gap']:+5.1f}%p)",
              file=sys.stderr)


if __name__ == "__main__":
    main()
