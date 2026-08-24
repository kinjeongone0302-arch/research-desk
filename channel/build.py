"""채널 아카이브 → docs/data/channel.json

게시물 원문 + 언급된 미국 종목 색인. 검색은 화면에서 하므로 여기선 색인만 만든다.
"""
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import tickers

OUT = BASE.parent / "docs" / "data" / "channel.json"
FIN = BASE.parent / "docs" / "data" / "fin_index.json"


def main():
    db = json.loads((BASE / "posts.json").read_text())
    posts = db["posts"]
    rows = json.loads(FIN.read_text())["rows"]
    valid = {r["t"] for r in rows if r["m"] == "US"}
    name = {r["t"]: r["n"] for r in rows if r["m"] == "US"}

    out, by_tk = [], defaultdict(list)
    for p in sorted(posts.values(), key=lambda x: x["t"], reverse=True):
        tks = [t for t, _ in tickers.extract(p["text"], valid)]
        rec = {"id": p["id"], "t": p["t"], "x": p["text"],
               "v": p.get("views"), "g": p.get("group")}
        if p.get("img"):
            rec["m"] = p["img"]
        if tks:
            rec["k"] = tks
            for t in tks:
                by_tk[t].append(p["id"])
        out.append(rec)

    mentions = [{"t": t, "n": name.get(t, t), "c": len(ids), "ids": ids[:200]}
                for t, ids in sorted(by_tk.items(), key=lambda kv: -len(kv[1]))]

    days = sorted({p["t"][:10] for p in posts.values()})
    doc = {"channel": db.get("channel"),
           "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
           "from": days[0] if days else None, "to": days[-1] if days else None,
           "count": len(out), "images": sum(1 for r in out if r.get("m")),
           "posts": out, "mentions": mentions}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
    print(f"→ {OUT}  ({OUT.stat().st_size/1024/1024:.1f} MB)")
    print(f"  게시물 {len(out):,} · 이미지 {doc['images']:,} · 종목 {len(mentions)}개")
    print("  상위: " + " ".join(f"{m['t']}({m['c']})" for m in mentions[:12]))


if __name__ == "__main__":
    main()
