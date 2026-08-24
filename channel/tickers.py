"""게시물에서 미국 종목 뽑아내기.

대문자 3~5글자만 보고 티커라고 하면 안 된다 — IT, AI, NOW, TECH, ALL, KEY 가 전부
실제 상장 티커라서 한국어 글에서 오탐이 쏟아진다. 그래서 세 갈래로만 인정한다.

  1) 한글 종목명 — 한국 채널에서 미국 주식은 대개 이렇게 불린다(엔비디아, 마이크론…)
  2) $TICKER 표기 — 명시적이라 무조건 인정
  3) 대문자 티커 — 단, 흔한 영어 낱말과 겹치는 것은 제외하고, 주변에 종목 얘기라는
     단서(주가·실적·급등 등)가 있을 때만
"""
import re

# 한글 표기 → 티커. 한국 증시 채널에서 실제로 쓰는 이름 위주.
KO = {
    "엔비디아": "NVDA", "엔디비아": "NVDA", "엔비댜": "NVDA",
    "브로드컴": "AVGO",
    "테슬라": "TSLA", "아마존": "AMZN", "구글": "GOOGL",
    "알파벳": "GOOGL", "마이크로소프트": "MSFT",
    "넷플릭스": "NFLX", "오라클": "ORCL", "코어위브": "CRWV", "코어위브": "CRWV",
    "네비우스": "NBIS", "팔란티어": "PLTR", "슈퍼마이크로": "SMCI", "슈마컴": "SMCI",
    "델테크놀로지": "DELL", "휴렛팩커드": "HPE", "시게이트": "STX",
    "웨스턴디지털": "WDC", "샌디스크": "SNDK", "퀄컴": "QCOM", "TSMC": "TSM",
    "티에스엠씨": "TSM", "ASML": "ASML", "에이에스엠엘": "ASML",
    "어플라이드머티리얼즈": "AMAT", "램리서치": "LRCX", "KLA": "KLAC",
    "마벨": "MRVL", "시놉시스": "SNPS", "케이던스": "CDNS", "아리스타": "ANET",
    "시스코": "CSCO", "코히런트": "COHR", "루멘텀": "LITE",
    "버티브": "VRT", "이튼": "ETN", "GE버노바": "GEV", "지이버노바": "GEV",
    "캐터필러": "CAT", "허니웰": "HON",
    "비스트라": "VST", "컨스텔레이션에너지": "CEG", "NRG": "NRG", "탈렌": "TLN",
    "블룸에너지": "BE", "퍼스트솔라": "FSLR", "엔페이즈": "ENPH",
    "일라이릴리": "LLY", "노보노디스크": "NVO", "유나이티드헬스": "UNH",
    "버크셔": "BRK-B", "JP모건": "JPM", "골드만삭스": "GS",
    "월마트": "WMT", "코스트코": "COST", "스타벅스": "SBUX", "나이키": "NKE",
    "보잉": "BA", "록히드마틴": "LMT", "RTX": "RTX", "팔로알토": "PANW",
    "크라우드스트라이크": "CRWD", "스노우플레이크": "SNOW", "데이터독": "DDOG",
    "세일즈포스": "CRM", "어도비": "ADBE", "우버": "UBER", "쿠팡": "CPNG",
    "로빈후드": "HOOD", "코인베이스": "COIN", "마이크로스트래티지": "MSTR",
    "리게티": "RGTI", "아이온큐": "IONQ", "디웨이브": "QBTS",
    "온세미": "ON", "텍사스인스트루먼트": "TXN", "아날로그디바이스": "ADI",
    "램버스": "RMBS", "크레도": "CRDO", "아스테라랩스": "ALAB",
    "센추리링크": "LUMN", "오클로": "OKLO", "뉴스케일": "SMR",
}

# 대문자 티커로 잡되 흔한 영어 낱말과 겹치는 것들 — 문맥 단서가 있어도 위험해 아예 뺀다
STOP = {
    "IT", "AI", "ON", "ALL", "NOW", "SO", "KEY", "CAR", "GOOD", "WELL", "ARE",
    "FOR", "TWO", "RUN", "NICE", "LOVE", "HOPE", "FAST", "OPEN", "REAL", "LIVE",
    "PLAY", "TEAM", "GAIN", "MAIN", "PLUS", "STEP", "WAVE", "LINK", "CASH",
    "COST", "LOW", "NEXT", "SAFE", "SHOP", "SITE", "SPOT", "TECH", "BIG", "NEW",
    "ONE", "SEE", "WIN", "TRUE", "FULL", "HIGH", "FREE", "DEAL", "BOOK", "BASE",
    "CORE", "EDGE", "PEAK", "RISE", "FLOW", "WORK", "DATA", "FUND", "US", "USA",
    "CEO", "CFO", "EPS", "PER", "PBR", "ROE", "GDP", "CPI", "FED", "FOMC", "ETF",
    "IPO", "MOU", "OEM", "ODM", "QOQ", "YOY", "CAGR", "HBM", "DDR", "SSD", "CPU",
    "GPU", "PCB", "CCL", "MLB", "ABF", "TSV", "EUV", "SIC", "PIM", "NPU", "ASIC",
    "IRA", "FTA", "OPEC", "WTI", "KOSPI", "SK", "LG", "GS", "CJ", "KT", "POSCO",
}

# 앞뒤에 다른 글자가 붙으면 다른 말이다 — '델'은 모델·델타에, '메타'는 메타버스에 걸린다.
GUARD = {
    # 앞뒤에 글자가 붙으면 다른 말이다 — 하나마이크론(국내 067310), 애플리케이션, 인텔리전스
    "MU": r"(?<!하나)마이크론",
    "AAPL": r"애플(?!리케)",
    "INTC": r"인텔(?!리)",
    "META": r"메타(?!버스|물질|데이터|인지)",
    "AMD": r"\bAMD\b",
    "DELL": r"\b(DELL|델(?=\s*테크|사|\s*서버|\s*주가))",
    "MSFT": r"\bMSFT\b|마이크로소프트",
    "TSM": r"\bTSMC?\b|티에스엠씨",
}

KNOWN = set(KO.values()) | {"META", "MSFT", "DELL", "AMD", "TSM"}

DOLLAR = re.compile(r"\$([A-Z]{1,5})\b")
UPPER = re.compile(r"\b([A-Z]{2,5})\b")
# 종목 얘기라는 단서
CONTEXT = re.compile(r"주가|실적|급등|급락|상승|하락|매수|매도|시총|밸류|가이던스|컨콜|"
                     r"어닝|EPS|목표주가|리포트|섹터|수주|출하|캐펙스|capex", re.I)


def extract(text, valid):
    """valid = 실제 존재하는 티커 집합. (티커, 근거) 목록을 돌려준다."""
    if not text:
        return []
    found = {}
    for ko, tk in KO.items():
        if ko in text and tk in valid:
            found.setdefault(tk, "한글명")
    for tk, pat in GUARD.items():
        if tk in valid and re.search(pat, text):
            found.setdefault(tk, "한글명")
    for m in DOLLAR.finditer(text):
        if m.group(1) in valid:
            found[m.group(1)] = "$표기"
    # 대문자 티커는 아무거나 받으면 FCF·ESS·DD·PC 같은 약어가 전부 종목이 된다.
    # 이 채널에서 실제로 거론되는 종목(KO 사전에 있는 것)으로만 한정한다.
    for m in UPPER.finditer(text):
        t = m.group(1)
        if t in KNOWN and t in valid and t not in STOP:
            found.setdefault(t, "티커")
    return sorted(found.items())
