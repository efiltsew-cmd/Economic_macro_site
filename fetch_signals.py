import json, os, urllib.request, urllib.parse, datetime as dt

FRED = os.environ.get("FRED_API_KEY")
S, errors = {}, []

def fred(sid, start):
    q = urllib.parse.urlencode(dict(series_id=sid, api_key=FRED, file_type="json", observation_start=start))
    o = json.load(urllib.request.urlopen("https://api.stlouisfed.org/fred/series/observations?" + q, timeout=30))["observations"]
    return [(x["date"], float(x["value"])) for x in o if x["value"] not in (".", "")]

def put(key, name, unit, pts, daily=True, n=900):
    if not pts:
        raise ValueError("데이터 없음")
    S[key] = dict(name=name, unit=unit, daily=daily, points=[(d, round(v, 4)) for d, v in pts][-n:])

def attempt(label, fn):
    try:
        fn()
    except Exception as e:
        errors.append(f"{label}: {e}"); print("실패:", label, e)

def yoy(p):
    return [(p[i][0], (p[i][1] / p[i - 12][1] - 1) * 100) for i in range(12, len(p))]

# (키, 이름, 단위, FRED 시리즈, 일별여부, 보관 개수, 배수)
SPEC = [
    ("t10y2y", "장단기 금리차 (10Y−2Y)", "%p", "T10Y2Y", True, 900, 1), ("t10y3m", "장단기 금리차 (10Y−3M)", "%p", "T10Y3M", True, 900, 1),
    ("hy", "하이일드 스프레드", "%p", "BAMLH0A0HYM2", True, 900, 1), ("ig", "투자등급 스프레드", "%p", "BAMLC0A0CM", True, 900, 1),
    ("nfci", "금융여건지수(NFCI)", "pt", "NFCI", False, 260, 1),
    ("icsa", "신규 실업수당 청구", "천 건", "ICSA", False, 260, 0.001), ("ic4w", "4주 평균", "천 건", "IC4WSA", False, 260, 0.001),
    ("jolts", "구인건수(JOLTS)", "천 건", "JTSJOL", False, 80, 1),
    ("bei5", "5년 BEI", "%", "T5YIE", True, 900, 1), ("bei10", "10년 BEI", "%", "T10YIE", True, 900, 1),
    ("bei5y5y", "5년 후 5년 기대인플레이션", "%", "T5YIFR", True, 900, 1), ("real10", "10년 실질금리(TIPS)", "%", "DFII10", True, 900, 1),
]

def usdjpy():
    import yfinance as yf
    c = yf.download("JPY=X", period="4y", auto_adjust=False, progress=False)["Close"]
    if hasattr(c, "columns"):
        c = c.iloc[:, 0]
    put("usdjpy", "달러/엔", "엔", [(i.strftime("%Y-%m-%d"), float(v)) for i, v in c.dropna().items()])

def main():
    today = dt.date.today()
    d_start = (today - dt.timedelta(days=1500)).isoformat(); w_start = (today - dt.timedelta(days=365 * 5)).isoformat(); m_start = (today - dt.timedelta(days=365 * 7)).isoformat()
    for key, name, unit, sid, daily, n, mult in SPEC:
        start = d_start if daily else (w_start if n == 260 else m_start)
        attempt(name, lambda: put(key, name, unit, [(d, v * mult) for d, v in fred(sid, start)], daily, n))
    attempt("평균시급", lambda: put("ahe", "평균시급 (전년 대비)", "%", yoy(fred("CES0500000003", m_start)), False, 80))
    attempt("달러/엔", usdjpy)  # FRED 엔/달러는 주 1회(월요일) 갱신되어 야후 일별 시세로 덮어씀
    kst = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")
    json.dump(dict(updated=kst, series=S, errors=errors), open("signals.json", "w", encoding="utf-8"), ensure_ascii=False)

if __name__ == "__main__":
    main()
