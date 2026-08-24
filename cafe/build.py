"""카페 아카이브 → docs/data/cafe.json"""
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE.parent / "fin"))
import dart
import download
import krnames

OUT = BASE.parent / "docs" / "data" / "cafe.json"


def main():
    posts = json.loads((BASE / "posts.json").read_text())["posts"]
    names = {c: n for c, (cc, n) in dart.corp_map().items()}
    table = krnames.build(names)

    out, by = [], defaultdict(int)
    label = {}
    for p in sorted(posts.values(), key=lambda x: x["t"], reverse=True):
        hits = krnames.extract(p["text"], table)
        rec = {"id": p["id"], "b": p["menu"], "t": p["t"], "s": p["title"],
               "x": p["text"], "v": p.get("views"), "c": p.get("comments")}
        # 네이버 CDN 은 브라우저 직접 호출을 막으므로(핫링크 차단) 받아둔 로컬 파일을 가리킨다
        got = [download.local_name(u) for u in (p.get("imgs") or [])
               if (download.MEDIA / download.local_name(u)).exists()]
        if got:
            rec["m"] = got
        if hits:
            rec["k"] = [c for c, _ in hits]
            for c, n in hits:
                by[c] += 1
                label[c] = n
        out.append(rec)

    stocks = [{"c": c, "n": label[c], "cnt": v}
              for c, v in sorted(by.items(), key=lambda kv: -kv[1])]
    days = sorted({p["t"][:10] for p in posts.values() if p["t"]})
    doc = {"cafe": "가치투자클럽 & 오르비스투자자문", "url": "orbisasset",
           "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
           "from": days[0] if days else None, "to": days[-1] if days else None,
           "count": len(out), "boards": sorted({p["menu"] for p in posts.values()}),
           "posts": out, "stocks": stocks}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
    print(f"→ {OUT}  ({OUT.stat().st_size/1024/1024:.1f} MB)")
    print(f"  글 {len(out)} · 종목 {len(stocks)}개 · 이미지 {sum(len(r.get('m') or []) for r in out)}장")
    print("  상위: " + " ".join(f"{s['n']}({s['cnt']})" for s in stocks[:10]))


if __name__ == "__main__":
    main()
