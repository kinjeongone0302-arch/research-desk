"""네이버 카페 게시판 아카이브 — 가치투자클럽(orbisasset)

목록은 비로그인으로도 열리지만 본문은 로그인이 필요하다. 세션 쿠키는 cafe/.cookies 에
두고(코드는 값을 화면에 찍지 않는다), 만료되면 갱신한다.
증분 수집 — 이미 받은 글은 건너뛴다.
"""
import html
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
COOKIES = BASE / ".cookies"
STORE = BASE / "posts.json"

CAFE_ID = 30917129
CAFE_URL = "orbisasset"
BOARDS = {2: "투데이탑픽", 22: "위클리노트"}
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
KST = timezone(timedelta(hours=9))

LIST = ("https://apis.naver.com/cafe-web/cafe2/ArticleListV2dot1.json"
        "?search.clubid={cafe}&search.menuid={menu}&search.page={page}&search.perPage=50")
ART = "https://apis.naver.com/cafe-web/cafe-articleapi/cafes/{cafe}/articles/{aid}"


def cookie_header():
    if not COOKIES.exists():
        raise SystemExit("cafe/.cookies 가 없다 — 네이버 세션 쿠키를 넣어야 한다")
    return "; ".join(l.strip() for l in COOKIES.read_text().splitlines() if "=" in l)


def get(url, ck):
    r = subprocess.run(["curl", "-s", "--max-time", "30", "--retry", "2", "-A", UA,
                        "-e", f"https://cafe.naver.com/{CAFE_URL}", "-H", f"Cookie: {ck}", url],
                       capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


def strip_html(s):
    """본문 HTML → 읽을 수 있는 텍스트. 표는 셀 구분만 남긴다."""
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s or "", flags=re.S | re.I)
    s = re.sub(r"</(p|div|tr|h\d|li)>", "\n", s, flags=re.I)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</t[dh]>", " | ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    # 본문에 이미지 자리표시자가 그대로 남는다 — 이미지는 따로 뽑으므로 지운다
    s = re.sub(r"\[\[\[CONTENT-ELEMENT-\d+\]\]\]", "", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t]+", " ", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def images(article):
    """이미지 URL. json.image.url 에 한 겹 더 들어가 있고, 썸네일 프록시로 여러 번
    감싸여 온다(dthumb-phinf ?src=...). 원본 주소만 풀어서 쓴다."""
    import urllib.parse
    out = []
    for el in article.get("contentElements") or []:
        if el.get("type") != "IMAGE":
            continue
        u = ((el.get("json") or {}).get("image") or {}).get("url")
        if not u:
            continue
        for _ in range(4):                       # 중첩된 프록시를 벗긴다
            m = re.search(r"[?&]src=([^&]+)", u)
            if not m:
                break
            u = urllib.parse.unquote(m.group(1)).strip('"')
        out.append(u.split("?")[0])
    return out[:20]


def load():
    if STORE.exists():
        try:
            return json.loads(STORE.read_text())
        except json.JSONDecodeError:
            pass
    return {"posts": {}}


def run(days=365):
    ck = cookie_header()
    db = load()
    since = datetime.now(KST) - timedelta(days=days)
    new = 0

    for menu, name in BOARDS.items():
        page, stop = 1, False
        while not stop:
            d = get(LIST.format(cafe=CAFE_ID, menu=menu, page=page), ck)
            res = (d or {}).get("message", {}).get("result", {})
            arts = res.get("articleList") or []
            if not arts:
                break
            for a in arts:
                aid = a.get("articleId")
                ts = a.get("writeDateTimestamp") or a.get("writeDate")
                when = datetime.fromtimestamp(ts / 1000, KST) if ts else None
                if when and when < since:
                    stop = True
                    break
                key = str(aid)
                if key in db["posts"]:
                    continue
                art = get(ART.format(cafe=CAFE_ID, aid=aid), ck) or {}
                # 성공 응답은 article 이 최상위에 온다. result 껍데기는 오류일 때만 붙는다.
                if art.get("result", {}).get("errorCode"):
                    raise SystemExit(f"카페 접근 거부 — 쿠키 만료로 보인다: "
                                     f"{art['result'].get('reason')}")
                a2 = art.get("article") or {}
                if not a2:
                    continue
                wd = a2.get("writeDate")
                when = datetime.fromtimestamp(wd / 1000, KST) if wd else when
                db["posts"][key] = {
                    "id": aid, "menu": name,
                    "t": when.strftime("%Y-%m-%d %H:%M") if when else "",
                    "title": a2.get("subject") or a.get("subject") or "",
                    "text": strip_html(a2.get("content")),
                    "imgs": images(a2),
                    "views": a2.get("readCount"),
                    "comments": a2.get("commentCount"),
                }
                new += 1
                time.sleep(0.25)
                if new % 20 == 0:
                    STORE.write_text(json.dumps(db, ensure_ascii=False, separators=(",", ":")))
                    print(f"  {name} {new}건", flush=True)
            if not res.get("hasNext"):
                break
            page += 1
        print(f"{name} 완료", flush=True)

    STORE.write_text(json.dumps(db, ensure_ascii=False, separators=(",", ":")))
    print(f"신규 {new}건 · 누적 {len(db['posts'])}건", flush=True)


if __name__ == "__main__":
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 365)
