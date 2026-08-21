"""DTCC 공개 공시 zip → 정규화된 CDS 체결 레코드."""
import csv
import datetime as dt
import io
import re
import zipfile
from pathlib import Path

RAW = Path(__file__).resolve().parent / "raw"

# 노셔널은 $5m 초과분이 '5,000,000+' 로 마스킹된다. 그 이하는 실측값이 그대로 나온다.
_CAP = re.compile(r"^([\d,]+)(\+?)$")


def _num(s):
    s = (s or "").strip().replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _date(s):
    s = (s or "").strip()[:10]
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        return None


def rows(venue, day):
    """venue: 'SEC'(단일물) | 'CFTC'(지수). day: date."""
    p = RAW / f"{venue}_{day:%Y_%m_%d}.zip"
    if not p.exists():
        return
    with zipfile.ZipFile(p) as z:
        for name in z.namelist():
            if not name.lower().endswith(".csv"):
                continue
            with z.open(name) as fh:
                text = io.TextIOWrapper(fh, encoding="utf-8-sig", newline="")
                yield from csv.DictReader(text)


def trades(venue, day):
    """가격 역산에 필요한 필드만 뽑아 정규화."""
    for r in rows(venue, day):
        if (r.get("Action type") or "") not in ("NEWT", "MODI"):
            continue
        exec_d = _date(r.get("Execution Timestamp"))
        mat = _date(r.get("Expiration Date"))
        if not exec_d or not mat or mat <= exec_d:
            continue

        m = _CAP.match((r.get("Notional amount-Leg 1") or "").strip())
        notional = float(m.group(1).replace(",", "")) if m else None
        capped = bool(m and m.group(2))

        pay = None
        if (r.get("Other payment type") or "").strip().upper() == "UFRO":
            pay = _num(r.get("Other payment amount"))

        yield {
            "id": (r.get("Dissemination Identifier") or "").strip(),
            "venue": venue,
            "file_date": day.isoformat(),
            "exec": exec_d.isoformat(),
            "maturity": mat.isoformat(),
            "tenor": round((mat - exec_d).days / 365.25, 3),
            "entity": (r.get("Underlying Asset Name") or "").strip(),
            "index": (r.get("UPI Underlier Name") or "").strip(),
            "fisn": (r.get("UPI FISN") or "").strip(),
            "notional": notional,
            "capped": capped,
            "ccy": (r.get("Notional currency-Leg 1") or "").strip(),
            "coupon": _num(r.get("Fixed rate-Leg 1")),
            "spread": _num(r.get("Spread-Leg 1")),      # 지수물은 여기에 스프레드가 직접 들어온다
            "upfront": pay,
            "cleared": (r.get("Cleared") or "").strip(),
        }


def all_days():
    seen = set()
    for p in sorted(RAW.glob("*.zip")):
        venue, y, m, d = p.stem.split("_")
        seen.add((venue, dt.date(int(y), int(m), int(d))))
    return sorted(seen, key=lambda x: (x[1], x[0]))
