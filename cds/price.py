"""ISDA 표준모형 근사 CDS 프라이서.

DTCC 공시에는 체결 스프레드가 없다. 표준화 이후 단일물 CDS 는 고정쿠폰(신흥국·한국은 100bp)
으로 거래되고 차액을 업프론트 현금으로 주고받기 때문에, 공시에 남는 건 업프론트 금액뿐이다.
그래서 업프론트를 역산해 par spread 를 뽑는다.

flat hazard 가정. 단일 만기 한 건에서 스프레드 하나를 뽑는 데는 hazard 곡선의 형태가
필요 없으므로 flat 으로 충분하고, 만기별로 따로 풀면 그 자체가 기간구조가 된다.
"""
import datetime as dt
import functools
import math

RECOVERY = 0.40      # 신흥국 시니어 무담보 표준
DISCOUNT = 0.038     # USD 무위험 flat. 만기 5년 기준 ±100bp 움직여도 스프레드는 0.3bp 미만 변화
DAY = 365.25

IMM_MONTHS = (3, 6, 9, 12)


def prev_imm(d):
    """직전 IMM 롤 일자(3·6·9·12월 20일). 미수이자 계산 기준일."""
    y, m = d.year, d.month
    for _ in range(5):
        cand = [dt.date(y, mm, 20) for mm in IMM_MONTHS]
        past = [c for c in cand if c <= d]
        if past:
            return max(past)
        y -= 1
    raise ValueError(d)


# 스프레드 역산은 이분법으로 hazard 를 120회 시도한다. 일정은 hazard 와 무관한데
# 매번 다시 만들면 그만큼 헛일이라, (거래일, 만기) 단위로 캐시한다.
@functools.lru_cache(maxsize=8192)
def _schedule(t0, maturity):
    """만기에서 분기 단위로 역산한 쿠폰 지급일. 마지막 조각은 t0 에서 잘린다."""
    out = []
    d = maturity
    while d > t0:
        out.append(d)
        m, y = d.month - 3, d.year
        if m <= 0:
            m += 12
            y -= 1
        d = dt.date(y, m, min(d.day, 28))
    return sorted(out)


@functools.lru_cache(maxsize=8192)
def _grid(t0, maturity):
    """일정에서 hazard 와 무관한 부분(경과연수·일수·할인계수)을 미리 계산해 둔다."""
    out = []
    prev = t0
    for d in _schedule(t0, maturity):
        t1 = (prev - t0).days / DAY
        t2 = (d - t0).days / DAY
        out.append((t1, t2, (d - prev).days / 360.0,
                    math.exp(-DISCOUNT * t2), math.exp(-DISCOUNT * (t1 + t2) / 2)))
        prev = d
    return tuple(out)


def legs(t0, maturity, hazard):
    """(risky PV01, protection leg PV) — 둘 다 노셔널 1 기준."""
    rpv01 = 0.0
    prot = 0.0
    for t1, t2, dcf, df, dfm in _grid(t0, maturity):
        q1 = math.exp(-hazard * t1)
        q2 = math.exp(-hazard * t2)
        rpv01 += dcf * df * (q2 + 0.5 * (q1 - q2))
        prot += (1 - RECOVERY) * dfm * (q1 - q2)
    return rpv01, prot


def upfront(t0, maturity, hazard, coupon=0.01):
    """clean 업프론트 (프로텍션 매수자가 내는 쪽이 +). 노셔널 1 기준."""
    rpv01, prot = legs(t0, maturity, hazard)
    return prot - coupon * rpv01


def par_spread(t0, maturity, hazard):
    rpv01, prot = legs(t0, maturity, hazard)
    return prot / rpv01 if rpv01 else float("nan")


def accrued(t0, coupon=0.01):
    """직전 IMM 이후 경과 쿠폰. 노셔널 1 기준."""
    return coupon * (t0 - prev_imm(t0)).days / 360.0


def _solve(t0, maturity, clean, coupon):
    """clean 업프론트(노셔널 1 기준, 부호 포함) → par spread. upfront 는 hazard 에 단조증가."""
    lo, hi = 1e-9, 3.0
    if clean < upfront(t0, maturity, lo, coupon) or clean > upfront(t0, maturity, hi, coupon):
        return float("nan")
    for _ in range(120):
        mid = 0.5 * (lo + hi)
        if upfront(t0, maturity, mid, coupon) < clean:
            lo = mid
        else:
            hi = mid
    return par_spread(t0, maturity, 0.5 * (lo + hi))


def branches(t0, maturity, cash_pts, coupon=0.01):
    """업프론트 현금에서 양쪽 해를 모두 낸다 → (low, high), 각각 nan 가능.

    공시에는 업프론트의 부호(누가 누구에게 냈는지)가 없다. 스프레드가 쿠폰보다 낮으면
    매도자가 매수자에게, 높으면 반대로 흐르므로 |cash| 하나에 해가 둘 붙는다.
    low  = 스프레드 < 쿠폰 (한국·일본 등 투자등급)
    high = 스프레드 > 쿠폰 (튀르키예 등 고위험 신흥국)
    어느 쪽인지는 종목 단위로 다수결한다 — 한 크레딧이 하루 만에 쿠폰선을 넘나들지는 않는다.

    미수이자: |clean| = |cash| - 직전 IMM 이후 경과쿠폰. 부호 규약이 공시에 없어
    한국물 700건의 IMM 롤 전후 점프로 실측해 정했다(ignore +6.4bp / 반대부호 +10.8bp /
    이 방식 +2.0bp). 남는 2bp 는 롤 월의 실제 변동으로 본다.
    """
    net = abs(cash_pts) - accrued(t0, coupon)
    return (_solve(t0, maturity, -net, coupon), _solve(t0, maturity, net, coupon))


def implied_spread(t0, maturity, cash_pts, coupon=0.01, side="low"):
    lo, hi = branches(t0, maturity, cash_pts, coupon)
    return lo if side == "low" else hi
