"""회사채 스프레드 기준선 — FRED 지수 OAS + 미 재무부 금리곡선.

둘 다 인증이 필요 없다. 개별 회사채 체결(FINRA TRACE)은 계정이 있어야 하므로
그건 trace.py 가 따로 맡고, 이 모듈은 그것 없이도 성립하는 부분을 담당한다.

OAS(option-adjusted spread)는 같은 만기 국채 대비 초과수익률이라 CDS 와 정의가 다르다.
레벨을 맞대면 안 되고, 시장 전체가 어디쯤인지 보는 기준선으로만 쓴다.
"""
import csv
import datetime as dt
import io
import subprocess
from pathlib import Path

CACHE = Path(__file__).resolve().parent / "cache"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="

# ICE BofA 미국 회사채 지수 OAS (단위: %)
OAS = {
    "AAA": "BAMLC0A1CAAA", "AA": "BAMLC0A2CAA", "A": "BAMLC0A3CA",
    "BBB": "BAMLC0A4CBBB", "BB": "BAMLH0A1HYBB", "B": "BAMLH0A2HYB",
    "CCC이하": "BAMLH0A3HYC", "하이일드": "BAMLH0A0HYM2", "투자등급": "BAMLC0A0CM",
}

TREASURY = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
            "daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve"
            "&field_tdr_date_value={year}&page&_format=csv")


# FRED 는 파이썬 기본 클라이언트로는 응답을 주지 않고(타임아웃), curl 도 커스텀
# User-Agent 를 붙이면 HTTP/2 스트림을 끊는다(exit 92). 기본 UA + HTTP/1.1 로 받는다.
def _get(url, dest, ttl_days=1):
    if dest.exists():
        age = dt.date.today() - dt.date.fromtimestamp(dest.stat().st_mtime)
        if age.days < ttl_days and dest.stat().st_size > 0:
            return dest.read_text()
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["curl", "-sL", "--http1.1", "--max-time", "60", "--retry", "2",
                        "-o", str(dest), url], capture_output=True)
    if r.returncode != 0 or not dest.exists() or dest.stat().st_size == 0:
        raise RuntimeError(f"내려받기 실패: {url}")
    return dest.read_text()


def oas(label, series_id):
    """{날짜: bp}. FRED 는 결측을 '.' 으로 준다."""
    text = _get(FRED + series_id, CACHE / f"fred_{series_id}.csv")
    out = {}
    for row in csv.DictReader(io.StringIO(text)):
        d = row.get("observation_date") or row.get("DATE")
        v = (row.get(series_id) or "").strip()
        if d and v and v != ".":
            out[d] = round(float(v) * 100, 1)
    return out


def treasury(years):
    """{날짜: {만기: %}}"""
    out = {}
    for y in years:
        text = _get(TREASURY.format(year=y), CACHE / f"ust_{y}.csv")
        for row in csv.DictReader(io.StringIO(text)):
            d = row.get("Date")
            if not d:
                continue
            mm, dd, yy = d.split("/")
            iso = f"{yy}-{mm}-{dd}"
            out[iso] = {k: float(v) for k, v in row.items()
                        if k != "Date" and (v or "").strip() not in ("", "N/A")}
    return dict(sorted(out.items()))
