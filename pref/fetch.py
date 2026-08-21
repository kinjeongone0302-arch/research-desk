"""본주 ↔ 우선주 짝 찾기 + 시세 수집.

DART 는 법인 단위라 우선주가 없다(005935 는 별도 고유번호가 없다). KRX 는 세션 쿠키를
요구한다. 네이버 시가총액 목록 API 가 우선주까지 포함해 한 번에 주므로 그걸 쓴다.
"""
import json
import re
import subprocess
import time
from pathlib import Path

CACHE = Path(__file__).resolve().parent / "cache"
UA = "Mozilla/5.0"
LIST = "https://m.stock.naver.com/api/stocks/marketValue/{mkt}?page={page}&pageSize=100"
SISE = ("https://api.finance.naver.com/siseJson.naver?symbol={code}"
        "&requestType=1&startTime={start}&endTime={end}&timeframe=day")

# 우선주 표기: 삼성전자우 / 현대차2우B / LG화학우 …
PREF_SUFFIX = re.compile(r"(\d?우[ABC]?)$")


def _curl(url, dest=None, ttl_days=1):
    import datetime as dt
    if dest and dest.exists():
        age = (dt.date.today() - dt.date.fromtimestamp(dest.stat().st_mtime)).days
        if age < ttl_days and dest.stat().st_size > 0:
            return dest.read_text()
    cmd = ["curl", "-sL", "--http1.1", "--max-time", "40", "--retry", "2",
           "-H", f"User-Agent: {UA}", url]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout:
        return None
    if dest:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(r.stdout)
    return r.stdout


def listings(refresh=False):
    """전 종목 {코드: 이름}. 우선주 포함."""
    out = {}
    for mkt in ("KOSPI", "KOSDAQ"):
        page = 1
        while True:
            f = CACHE / f"list_{mkt}_{page}.json"
            txt = _curl(LIST.format(mkt=mkt, page=page), f, ttl_days=0 if refresh else 3)
            if not txt:
                break
            d = json.loads(txt)
            rows = d.get("stocks") or []
            for r in rows:
                out[r["itemCode"]] = r["stockName"]
            if page * 100 >= (d.get("totalCount") or 0):
                break
            page += 1
            time.sleep(0.1)
    return out


def pairs(names):
    """(보통주코드, 보통주명, 우선주코드, 우선주명) 목록.

    이름에서 우선주 접미사를 떼면 보통주 이름이 된다. 코드도 앞 5자리가 같은지로 한 번 더 거른다
    — '연우'처럼 이름이 우로 끝나는 보통주를 걸러내기 위해서다.
    """
    by_name = {}
    for c, n in names.items():
        by_name.setdefault(n, c)
    out = []
    for c, n in names.items():
        m = PREF_SUFFIX.search(n)
        if not m:
            continue
        base = n[: m.start()].strip()
        bc = by_name.get(base)
        if bc and bc[:5] == c[:5] and bc != c:
            out.append((bc, base, c, n))
    return sorted(set(out))


def closes(code, start="20200101", end=None):
    """{YYYYMMDD: 종가}"""
    import datetime as dt
    end = end or dt.date.today().strftime("%Y%m%d")
    txt = _curl(SISE.format(code=code, start=start, end=end),
                CACHE / f"sise_{code}.txt")
    if not txt:
        return {}
    return {m.group(1): float(m.group(2)) for m in
            re.finditer(r'\["(\d{8})",\s*[\d.]+,\s*[\d.]+,\s*[\d.]+,\s*([\d.]+),', txt)}
