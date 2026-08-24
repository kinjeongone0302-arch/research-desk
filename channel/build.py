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

    # 사진 여러 장을 한 번에 올리면 텔레그램은 그걸 여러 메시지로 쪼개 보낸다(같은 grouped_id).
    # 그대로 두면 캡션 한 줄에 사진 열 장짜리 글이 열 개로 흩어진다 — 하나로 합친다.
    merged, groups = [], {}
    for p in sorted(posts.values(), key=lambda x: x["t"], reverse=True):
        g = p.get("group")
        if g and g in groups:
            head = groups[g]
            if p.get("img"):
                head["_imgs"].append(p["img"])
            if p["text"] and len(p["text"]) > len(head["_text"]):
                head["_text"] = p["text"]          # 캡션은 보통 한 장에만 달린다
            head["_views"] = max(head["_views"] or 0, p.get("views") or 0)
            continue
        rec = {"id": p["id"], "t": p["t"], "_text": p["text"],
               "_views": p.get("views"), "_imgs": [p["img"]] if p.get("img") else []}
        if g:
            groups[g] = rec
        merged.append(rec)

    out, by_tk = [], defaultdict(list)
    for r in merged:
        tks = [t for t, _ in tickers.extract(r["_text"], valid)]
        rec = {"id": r["id"], "t": r["t"], "x": r["_text"], "v": r["_views"] or None}
        if r["_imgs"]:
            rec["m"] = r["_imgs"]
        if tks:
            rec["k"] = tks
            for t in tks:
                by_tk[t].append(r["id"])
        out.append(rec)

    mentions = [{"t": t, "n": name.get(t, t), "c": len(ids), "ids": ids[:200]}
                for t, ids in sorted(by_tk.items(), key=lambda kv: -len(kv[1]))]

    days = sorted({p["t"][:10] for p in posts.values()})
    doc = {"channel": db.get("channel"),
           "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
           "from": days[0] if days else None, "to": days[-1] if days else None,
           "count": len(out), "images": sum(len(r.get("m") or []) for r in out),
           "posts": out, "mentions": mentions}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
    print(f"→ {OUT}  ({OUT.stat().st_size/1024/1024:.1f} MB)")
    print(f"  게시물 {len(out):,} · 이미지 {doc['images']:,} · 종목 {len(mentions)}개")
    print("  상위: " + " ".join(f"{m['t']}({m['c']})" for m in mentions[:12]))


if __name__ == "__main__":
    main()
