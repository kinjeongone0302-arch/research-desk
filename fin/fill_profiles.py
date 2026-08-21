"""개요(company.json) 채우기. 종목당 1회 호출이라 한 번에 다 받으면 DART 가 IP 를 막는다.
매출 큰 순으로 회차를 나눠 받고, 캐시가 곧 진행률이다."""
import json
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import dart

KR = BASE.parent / "site" / "data" / "fin" / "KR"


def size_map():
    out = {}
    for f in KR.glob("*.json"):
        try:
            d = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        a = d.get("annual") or []
        out[f.stem] = (a[-1].get("rev") if a else 0) or 0
    return out


if __name__ == "__main__":
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    m, order = dart.corp_map(), size_map()
    for r in range(rounds):
        if not dart.alive():
            print("  DART 응답 없음 — 중단", flush=True)
            break
        p = dart.profiles(m, budget=400, order=order)
        print(f"  {r+1}회차 → 개요 {len(p)}/{len(m)}", flush=True)
        if len(p) >= len(m):
            break
        time.sleep(15)
