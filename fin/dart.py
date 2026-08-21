"""DART 수집 — 상장사 개요 + 주요계정 재무제표.

종목 하나씩 부르지 않는다. 다중회사 주요계정 API 는 한 번에 100개사를 받고,
응답에 당기·전기·전전기가 함께 실려 호출 1회에 3년치가 딸려온다.
개요(company.json)만 종목별 호출이라 캐시해두고 새 종목만 채운다.
"""
import json
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BASE = Path(__file__).resolve().parent
CACHE = BASE / "cache"
API = "https://opendart.fss.or.kr/api"

REPORTS = {"11011": "사업", "11012": "반기", "11013": "1분기", "11014": "3분기"}
# 분기 라벨은 정렬되는 형태로 쓴다. '2025반기' 와 '20253분기' 를 문자열로 비교하면 순서가 뒤집힌다.
LABELS = {"11012": "H1", "11013": "Q1", "11014": "Q3"}


def key():
    for line in (Path.home() / "backlog-bot" / ".env").read_text().splitlines():
        if line.startswith("DART_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("DART_API_KEY 를 찾을 수 없다 (~/backlog-bot/.env)")


# DART 는 짧은 시간에 요청이 몰리면 응답 대신 연결을 끊어버린다(ConnectionReset).
# 상태코드가 아니라 소켓 단에서 끊기므로 재시도 간격을 넉넉히 벌려야 회복된다.
def get(path, **params):
    params["crtfc_key"] = key()
    url = f"{API}/{path}?" + urllib.parse.urlencode(params)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(url, timeout=40) as r:
                return json.loads(r.read())
        except Exception:
            if attempt == 4:
                return None
            time.sleep((3, 10, 30, 60)[attempt])


def corp_map(refresh=False):
    """상장 종목코드 → (고유번호, 정식명). 전체 목록은 zip 으로 한 번에 받는다."""
    xml = CACHE / "CORPCODE.xml"
    if refresh or not xml.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        z = CACHE / "corpcode.zip"
        urllib.request.urlretrieve(f"{API}/corpCode.xml?crtfc_key={key()}", z)
        with zipfile.ZipFile(z) as f:
            f.extractall(CACHE)
    out = {}
    for e in ET.parse(xml).getroot().iter("list"):
        code = (e.findtext("stock_code") or "").strip()
        if code and len(code) == 6:
            out[code] = (e.findtext("corp_code"), e.findtext("corp_name"))
    return out


def alive():
    """차단 여부를 한 번만 확인한다. 막힌 상태에서 수천 건을 던지면 백오프만 쌓인다."""
    return dict(get("company.json", corp_code="00126380") or {}).get("status") == "000"


def profiles(codes, workers=2, budget=400, order=None):
    """종목별 개요. 한 번 받은 건 캐시에서 읽는다."""
    d = CACHE / "kr_profile"
    d.mkdir(parents=True, exist_ok=True)

    def one(item):
        stock, (corp, _) = item
        f = d / f"{corp}.json"
        if f.exists():
            return True
        r = get("company.json", corp_code=corp)
        if r and r.get("status") == "000":
            f.write_text(json.dumps(r, ensure_ascii=False))
            time.sleep(0.5)
            return True
        # 상태코드가 정상이 아니어도(폐지 등) 재조회를 막기 위해 빈 파일로 표시
        if r is not None:
            f.write_text("{}")
            return True
        return False

    todo = [(s, v) for s, v in codes.items() if not (d / f"{v[0]}.json").exists()]
    # 한 회차에 다 못 받으므로 큰 회사부터 채운다 — 검색될 확률이 높은 순서다.
    if order:
        todo.sort(key=lambda it: -(order.get(it[0]) or 0))
    todo = todo[:budget]
    # DART 차단 상태에서 수천 건을 재시도하면 백오프만 쌓여 몇 시간이 날아간다.
    # 연속 실패가 이어지면 이번 판은 접고 다음 실행에서 이어받는다 (캐시가 진행률).
    if todo:
        fails = 0
        with ThreadPoolExecutor(workers) as ex:
            for got in ex.map(one, todo):
                fails = 0 if got else fails + 1
                if fails >= 12:
                    print("  DART 응답 없음 — 이번 회차 개요 수집 중단 (다음 실행에서 이어받음)")
                    break
    out = {}
    for stock, (corp, _) in codes.items():
        f = d / f"{corp}.json"
        if f.exists():
            try:
                out[stock] = json.loads(f.read_text())
            except json.JSONDecodeError:
                pass
    return out


def accounts(corp_codes, year, reprt, workers=2):
    """다중회사 주요계정. 100개사씩 끊어 부른다."""
    d = CACHE / "kr_acct"
    d.mkdir(parents=True, exist_ok=True)
    batches = [corp_codes[i:i + 100] for i in range(0, len(corp_codes), 100)]

    def one(iv):
        i, batch = iv
        f = d / f"{year}_{reprt}_{i:03d}.json"
        if f.exists():
            try:
                return json.loads(f.read_text())
            except json.JSONDecodeError:
                pass
        r = get("fnlttMultiAcnt.json", corp_code=",".join(batch),
                bsns_year=str(year), reprt_code=reprt)
        rows = r.get("list", []) if r and r.get("status") == "000" else []
        f.write_text(json.dumps(rows, ensure_ascii=False))
        time.sleep(0.5)
        return rows

    with ThreadPoolExecutor(workers) as ex:
        return [row for rows in ex.map(one, enumerate(batches)) for row in rows]
