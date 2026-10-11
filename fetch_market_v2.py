import json, os, bisect, urllib.request, urllib.parse, datetime as dt

FRED, ECOS = os.environ.get("FRED_API_KEY"), os.environ.get("ECOS_API_KEY")
today = dt.date.today()
S, errors = {}, []

def get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)

def fred(sid, start):
    q = urllib.parse.urlencode(dict(series_id=sid, api_key=FRED, file_type="json", observation_start=start))
    o = get("https://api.stlouisfed.org/fred/series/observations?" + q)["observations"]
    return [(x["date"], float(x["value"])) for x in o if x["value"] not in (".", "")]

def scale_factor(units):  # FRED 단위를 십억 달러로 환산하는 배수
    u = (units or "").lower()
    return 1e-3 if "millions" in u else 1.0 if "billions" in u else 1e-6 if "thousands" in u else 1e3 if "trillions" in u else 1.0

def fred_b(sid, start):  # 십억 달러 단위로 환산한 FRED 시계열
    q = urllib.parse.urlencode(dict(series_id=sid, api_key=FRED, file_type="json"))
    f = scale_factor(get("https://api.stlouisfed.org/fred/series?" + q)["seriess"][0].get("units"))
    return [(d, v * f) for d, v in fred(sid, start)]

def ecos(code, start, end):
    stat, cyc, item = code
    fmt = "%Y%m%d" if cyc == "D" else "%Y%m"
    url = f"https://ecos.bok.or.kr/api/StatisticSearch/{ECOS}/json/kr/1/10000/{stat}/{cyc}/{start.strftime(fmt)}/{end.strftime(fmt)}/{item}"
    out = []
    for r in get(url)["StatisticSearch"]["row"]:
        t = r["TIME"]
        out.append((f"{t[:4]}-{t[4:6]}-{t[6:8]}" if len(t) == 8 else f"{t[:4]}-{t[4:6]}-01", float(r["DATA_VALUE"].replace(",", ""))))
    return out

def put(key, name, unit, pts, daily=True, n=900):
    if not pts:
        raise ValueError("데이터 없음")
    S[key] = dict(name=name, unit=unit, daily=daily, points=[(d, round(v, 4)) for d, v in pts][-n:])

def attempt(label, fn):
    try:
        fn()
    except Exception as e:
        errors.append(f"{label}: {e}")
        print("실패:", label, e)

def net_liquidity(walcl, tga, rrp):
    def asof(p, d):
        i = bisect.bisect_right([x[0] for x in p], d) - 1
        return p[i][1] if i >= 0 else None
    out = []
    for d, v in walcl:
        t, r = asof(tga, d), asof(rrp, d)
        if t is not None and r is not None:
            out.append((d, v - t - r))
    return out

def cmf_calc(x, n=20):  # x: High/Low/Close/Volume 열을 가진 DataFrame
    rng = (x.High - x.Low).replace(0, float("nan"))
    mfv = ((((x.Close - x.Low) - (x.High - x.Close)) / rng) * x.Volume).fillna(0).tail(n).sum()
    cmf = mfv / x.Volume.tail(n).sum()
    dv = x.Close * x.Volume
    return round(float(cmf), 3), round(float(dv.tail(5).mean() / dv.tail(60).mean()), 2), round(float((x.Close.iloc[-1] / x.Close.iloc[-21] - 1) * 100), 2)

ASSETS = [("주식", "SPY", "S&P 500"), ("주식", "QQQ", "나스닥 100"), ("주식", "IWM", "소형주"), ("주식", "EFA", "선진국"), ("주식", "EEM", "신흥국"),
          ("채권", "TLT", "미 장기국채"), ("채권", "IEF", "미 중기국채"), ("채권", "HYG", "하이일드"), ("채권", "LQD", "투자등급 회사채"),
          ("대체·통화", "GLD", "금"), ("대체·통화", "DBC", "원자재 종합"), ("대체·통화", "USO", "원유"), ("대체·통화", "UUP", "달러")]
SECT = [("섹터", t, n) for t, n in (("XLK", "IT"), ("XLF", "금융"), ("XLY", "임의소비재"), ("XLC", "커뮤니케이션 서비스"), ("XLI", "산업재"), ("XLB", "소재"),
                                   ("XLE", "에너지"), ("XLV", "헬스케어"), ("XLP", "필수소비재"), ("XLU", "유틸리티"), ("XLRE", "부동산"))]

def proxy():
    import yfinance as yf
    rows = ASSETS + SECT
    df = yf.download([t for _, t, _ in rows], period="1y", auto_adjust=False, progress=False)
    out = []
    for g, t, n in rows:
        try:
            x = df.xs(t, axis=1, level=1)[["High", "Low", "Close", "Volume"]].dropna()
            c, d, r = cmf_calc(x)
            out.append(dict(g=g, t=t, n=n, cmf=c, dv=d, r20=r))
        except Exception as e:
            errors.append(f"{t} 자금흐름: {e}")
    return out

def futures():
    import yfinance as yf
    m = {"gold": ("GC=F", "금", "$/oz"), "silver": ("SI=F", "은", "$/oz"), "copper": ("HG=F", "구리", "$/lb"),
         "wti": ("CL=F", "WTI유", "$/bbl"), "brent": ("BZ=F", "브렌트유", "$/bbl"),
         "natgas": ("NG=F", "천연가스", "$/MMBtu")}
    df = yf.download([v[0] for v in m.values()], period="4y", auto_adjust=False, progress=False)["Close"]
    for k, (t, n, u) in m.items():
        attempt(n, lambda: put(k, n, u, [(i.strftime("%Y-%m-%d"), float(v)) for i, v in df[t].dropna().items()]))

def main():
    d_start = (today - dt.timedelta(days=1500)).isoformat()
    w_start = (today - dt.timedelta(days=365 * 5)).isoformat()
    m_start = (today - dt.timedelta(days=365 * 7)).isoformat()
    attempt("미국 10년", lambda: put("us10y", "미국 10년 국채", "%", fred("DGS10", d_start)))
    attempt("미국 30년", lambda: put("us30y", "미국 30년 국채", "%", fred("DGS30", d_start)))
    attempt("한국 3년", lambda: put("kr3y", "한국 국채 3년", "%", ecos(("817Y002", "D", "010200000"), today - dt.timedelta(days=1500), today)))
    attempt("달러지수", lambda: put("usd_idx", "달러지수(Broad)", "pt", fred("DTWEXBGS", d_start)))
    attempt("원자재 선물", futures)
    for k, n, u, sid in (("wti", "WTI유", "$/bbl", "DCOILWTICO"), ("brent", "브렌트유", "$/bbl", "DCOILBRENTEU"), ("natgas", "천연가스", "$/MMBtu", "DHHNGSP")):
        if k not in S:
            attempt(n + " (FRED)", lambda: put(k, n, u, fred(sid, d_start)))
    attempt("두바이유", lambda: put("dubai", "두바이유(월평균)", "$/bbl", fred("POILDUBUSDM", m_start), daily=False, n=80))
    attempt("니켈", lambda: put("nickel", "니켈(월평균)", "$/t", fred("PNICKUSDM", m_start), daily=False, n=80))
    def liq():
        w, t, r = fred_b("WALCL", w_start), fred_b("WTREGEN", w_start), fred_b("RRPONTSYD", w_start)
        put("fed_assets", "연준 총자산", "십억$", w, False, 260)
        put("tga", "재무부 일반계정", "십억$", t, False, 260)
        put("rrp", "역레포", "십억$", r, True, 900)
        put("net_liq", "순유동성", "십억$", net_liquidity(w, t, r), False, 260)
    attempt("연준 유동성", liq)
    attempt("MMF 소매", lambda: put("mmf_retail", "소매 MMF", "십억$", fred_b("WRMFSL", w_start), False, 260))
    attempt("MMF 기관", lambda: put("mmf_inst", "기관 MMF", "십억$", fred_b("WIMFSL", w_start), False, 260))
    p = []
    attempt("ETF 자금흐름", lambda: p.extend(proxy()))
    kst = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")
    json.dump(dict(updated=kst, series=S, proxy=p, errors=errors), open("market.json", "w", encoding="utf-8"), ensure_ascii=False)

if __name__ == "__main__":
    main()
