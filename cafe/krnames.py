"""본문에서 국내 상장사 이름 뽑아내기.

단순 부분문자열 검색은 못 쓴다 — 'SK'는 'SK하이닉스' 안에, '테스'는 '테스나' 안에,
'레이'는 '레이저' 안에 들어 있다. 두 가지로 거른다.

  1) 긴 이름부터 찾고 그 구간을 소비 처리 — 'SK하이닉스'를 잡으면 그 안의 'SK'는 못 잡는다
  2) 짧은 이름은 뒤에 오는 글자를 본다 — 한글이 이어지면 다른 낱말이고,
     조사(은/는/이/가/의…)나 공백·부호면 종목명이다
"""
import re

PARTICLES = ("은", "는", "이", "가", "을", "를", "의", "도", "만", "와", "과", "에",
             "로", "으로", "에서", "부터", "까지", "이나", "나", "랑", "이랑", "보다",
             "처럼", "같이", "및", "등", "주", "주가", "실적", "이익", "매출")
HANGUL = re.compile(r"[가-힣]")
SHORT = 3          # 이 길이 이하는 경계 검사를 건다

# 이름이 흔한 낱말과 겹쳐 어떤 규칙으로도 못 거르는 종목
BLOCK = {"전방", "도움", "리드", "대상", "만호", "태양", "우리", "한국", "세방", "삼진",
         "이月", "가온", "동양", "신원", "국제", "중앙", "표준", "미래", "선진", "기업",
         "일신", "성원", "대한", "고려", "혜인", "다올", "체시스", "우진", "한창"}


# 흔히 부르는 이름이 정식명과 다른 종목. 정식명만으로는 못 잡거나, 짧은 이름이
# 이 별칭에 파묻혀 오탐이 난다(두산테스나 → '테스나', 그 안의 '테스'는 다른 종목).
ALIAS = {
    "131970": ["두산테스나", "테스나"],
    "000660": ["SK하이닉스", "하이닉스"],
    "042660": ["한화오션"],
    "012450": ["한화에어로스페이스", "한화에어로"],
    "034020": ["두산에너빌리티", "두산에너"],
    "010140": ["삼성중공업"],
    "009540": ["HD한국조선해양", "한국조선해양"],
    "329180": ["HD현대중공업", "현대중공업"],
    "267250": ["HD현대"],
    "047050": ["포스코인터내셔널", "포스코인터"],
    "005490": ["POSCO홀딩스", "포스코홀딩스", "포스코"],
    "051910": ["LG화학"],
    "373220": ["LG에너지솔루션", "LG엔솔", "엘지엔솔"],
    "006400": ["삼성SDI"],
    "096770": ["SK이노베이션", "SK이노"],
    "000270": ["기아"],
    "005380": ["현대차"],
    "192820": ["코스맥스"],
    "090430": ["아모레퍼시픽", "아모레"],
}


def build(names):
    """{종목코드: 이름} → 검색용 (이름, 코드) 목록. 긴 이름부터."""
    out = []
    seen = set()
    for code, alts in ALIAS.items():
        for a in alts:
            if (a, code) not in seen:
                out.append((a, code))
                seen.add((a, code))
    for c, n in names.items():
        if n and n not in BLOCK and (n, c) not in seen:
            out.append((n, c))
    out.sort(key=lambda x: -len(x[0]))
    return out


def extract(text, table, limit=40):
    """(종목코드, 이름) 목록. 같은 종목은 한 번만."""
    if not text:
        return []
    used = [False] * len(text)
    found = {}
    for name, code in table:
        start = 0
        L = len(name)
        while True:
            i = text.find(name, start)
            if i < 0:
                break
            start = i + 1
            if any(used[i:i + L]):
                continue                      # 더 긴 이름이 이미 차지한 자리
            if L <= SHORT:
                nxt = text[i + L:i + L + 4]
                if HANGUL.match(nxt[:1]):
                    # 조사면 종목명이 끝난 것이고, 그 조사 뒤에 또 한글이 붙으면
                    # 조사가 아니라 낱말의 일부다 ('테스나' 의 '나')
                    par = next((q for q in PARTICLES if nxt.startswith(q)), None)
                    if not par or HANGUL.match(nxt[len(par):len(par) + 1] or ""):
                        continue
                prev = text[i - 1:i]
                if HANGUL.match(prev):
                    continue                  # 앞에도 한글이 붙어 있으면 다른 낱말
            elif text[i - 1:i] and HANGUL.match(text[i - 1:i]):
                continue                      # 온디바이스 안의 디바이스 같은 경우
            for j in range(i, i + L):
                used[j] = True
            found.setdefault(code, name)
            break                             # 한 글에서 같은 종목은 한 번만
        if len(found) >= limit:
            break
    return sorted(found.items(), key=lambda kv: -len(kv[1]))
