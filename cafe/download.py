"""카페 이미지 내려받기 → docs/cafemedia/

네이버 이미지 CDN 은 브라우저에서 직접 부르면 막는다(핫링크 차단). 서버에서 받아
같이 배포해야 화면에 뜬다. 파일명은 URL 해시로 정해 중복을 피하고, 이미 받은 건 건너뛴다.
"""
import hashlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BASE = Path(__file__).resolve().parent
STORE = BASE / "posts.json"
MEDIA = BASE.parent / "docs" / "cafemedia"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"


def local_name(url):
    ext = ".png" if ".png" in url.lower() else ".jpg"
    return hashlib.sha1(url.encode()).hexdigest()[:16] + ext


def one(url):
    f = MEDIA / local_name(url)
    if f.exists() and f.stat().st_size > 0:
        return True
    r = subprocess.run(["curl", "-sL", "--max-time", "40", "--retry", "1", "-A", UA,
                        "-e", "https://cafe.naver.com/orbisasset", "-o", str(f), url],
                       capture_output=True)
    if r.returncode != 0 or not f.exists() or f.stat().st_size == 0:
        f.unlink(missing_ok=True)
        return False
    return True


def main():
    MEDIA.mkdir(parents=True, exist_ok=True)
    posts = json.loads(STORE.read_text())["posts"]
    urls = []
    for p in posts.values():
        for u in p.get("imgs") or []:
            if u not in urls:
                urls.append(u)
    todo = [u for u in urls if not (MEDIA / local_name(u)).exists()]
    print(f"이미지 {len(urls):,}장 · 받을 것 {len(todo):,}장", flush=True)
    done = 0
    with ThreadPoolExecutor(6) as ex:
        for ok in ex.map(one, todo):
            done += 1
            if done % 200 == 0:
                print(f"  {done:,}/{len(todo):,}", flush=True)
    have = len(list(MEDIA.glob("*")))
    print(f"완료 — 보유 {have:,}장 · {sum(f.stat().st_size for f in MEDIA.glob('*'))/1e6:.0f}MB", flush=True)


if __name__ == "__main__":
    main()
