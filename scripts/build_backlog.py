"""~/backlog-bot 의 수집 결과를 대시보드용으로 슬림화.

원본은 DART 원문 파싱 흔적(dropped_rows, table_parts 등)을 다 들고 있어 600KB 다.
화면에 필요한 값만 남기고 증감률은 미리 계산해 둔다.
"""
import json
import datetime as dt
from pathlib import Path

SRC = Path.home() / "backlog-bot" / "data.json"
OUT = Path(__file__).resolve().parents[1] / "site" / "data" / "backlog.json"


def pct(cur, prev):
    if not prev or prev <= 0 or cur is None:
        return None
    return round((cur / prev - 1) * 100, 1)


def main():
    src = json.loads(SRC.read_text())
    stocks = []
    for s in src["stocks"]:
        periods = [p for p in s.get("periods", []) if p.get("backlog")]
        periods.sort(key=lambda p: p.get("asof") or "")
        slim = []
        for i, p in enumerate(periods):
            prev = periods[i - 1]["backlog"] if i else None
            # 같은 분기 전년 값 — 반기/분기 공시가 섞여 있어 라벨의 연도만 바꿔 찾는다
            label = p.get("period", "")
            yoy_base = next((q["backlog"] for q in periods[:i]
                             if q.get("period", "")[4:] == label[4:]
                             and q.get("period", "")[:4] == str(int(label[:4]) - 1)), None) \
                if label[:4].isdigit() else None
            slim.append({
                "period": label,
                "asof": p.get("asof"),
                "backlog": p["backlog"],
                "qoq": pct(p["backlog"], prev),
                "yoy": pct(p["backlog"], yoy_base),
                "rcept": p.get("rcept_no"),
                "breakdown": [{"k": b["key"], "v": b["backlog"]}
                              for b in (p.get("breakdown") or [])
                              if b.get("backlog")][:12],
            })
        last = slim[-1] if slim else None
        stocks.append({
            "code": s["code"], "name": s["name"], "sector": s["sector"],
            "status": s["status"], "revenue": s.get("revenue"),
            "revenue_year": s.get("revenue_year"),
            "cover": (round(last["backlog"] / s["revenue"], 2)
                      if last and s.get("revenue") else None),
            "last": last["period"] if last else None,
            "last_backlog": last["backlog"] if last else None,
            "qoq": last["qoq"] if last else None,
            "yoy": last["yoy"] if last else None,
            "periods": slim,
        })
    stocks.sort(key=lambda x: (x["sector"], -(x["last_backlog"] or 0)))
    doc = {
        "generated_at": src.get("generated_at"),
        "built_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": "DART 정기보고서 원문 파싱 (~/backlog-bot)",
        "sector_order": src["sector_order"],
        "sector_groups": src["sector_groups"],
        "stocks": stocks,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
    ok = [s for s in stocks if s["status"] == "ok"]
    print(f"→ {OUT}  ({OUT.stat().st_size/1024:.0f} KB)  {len(ok)}/{len(stocks)} 종목")


if __name__ == "__main__":
    main()
