import json, os, urllib.request, urllib.parse, datetime as dt, statistics as st

FRED = os.environ.get("FRED_API_KEY")
PH = ["초기", "중간", "후기", "침체"]
# 섹터, ETF, 피델리티 표(초기·중간·후기·침체): ++=2, +=1, 빈칸=0, -=-1, --=-2
SECT = [
    ("금융", "XLF", (1, 0, 0, -1)), ("부동산", "XLRE", (2, -1, 1, -2)),
    ("임의소비재", "XLY", (2, 0, -2, 0)), ("IT", "XLK", (1, 1, -1, -2)),
    ("산업재", "XLI", (2, 0, 0, -2)), ("소재", "XLB", (1, -2, 0, -1)),
    ("필수소비재", "XLP", (-2, -1, 1, 2)), ("헬스케어", "XLV", (-2, 0, 0, 2)),
    ("에너지", "XLE", (-2, 0, 2, -2)), ("커뮤니케이션 서비스", "XLC", (0, 1, 0, -1)),
    ("유틸리티", "XLU", (-2, -1, 1, 2)),
]

def get_prices():
    tick = [e for _, e, _ in SECT] + ["SPY"]
    try:
        import yfinance as yf
        df = yf.download(tick, period="2y", auto_adjust=True, progress=False)["Close"]
        out = {t: [(i.strftime("%Y-%m-%d"), float(v)) for i, v in df[t].dropna().items()] for t in tick}
        if all(len(v) > 130 for v in out.values()):
            return out
    except Exception as e:
        print("yfinance 실패:", e)
    out = {}  # 대체 출처: Stooq
    for t in tick:
        raw = urllib.request.urlopen(f"https://stooq.com/q/d/l/?s={t.lower()}.us&i=d", timeout=30).read().decode()
        rows = [r.split(",") for r in raw.strip().splitlines()[1:]]
        out[t] = [(r[0], float(r[4])) for r in rows if len(r) > 4][-520:]
        if len(out[t]) < 130:
            raise RuntimeError(f"{t} 가격 데이터를 가져오지 못했습니다")
    return out

def fred(sid, start):
    q = urllib.parse.urlencode(dict(series_id=sid, api_key=FRED, file_type="json", observation_start=start))
    o = json.load(urllib.request.urlopen("https://api.stlouisfed.org/fred/series/observations?" + q, timeout=30))["observations"]
    return [(x["date"], float(x["value"])) for x in o if x["value"] not in (".", "")]

def ret(p, n):
    return (p[-1][1] / p[-1 - n][1] - 1) * 100

def compute_market(px):
    spy = px["SPY"]
    rows = []
    for name, etf, w in SECT:
        p = px[etf]
        r = {k: round(ret(p, n), 2) for k, n in (("d1", 1), ("w1", 5), ("m1", 21), ("m3", 63), ("m6", 126))}
        rel = {k: round(r[k] - ret(spy, n), 2) for k, n in (("m3", 63), ("m6", 126))}
        rows.append(dict(name=name, etf=etf, w=list(w), ret=r, rel=rel, rs=0.5 * rel["m3"] + 0.5 * rel["m6"]))
    mu, sd = st.mean(x["rs"] for x in rows), st.pstdev(x["rs"] for x in rows) or 1
    for x in rows:
        x["z"] = round((x.pop("rs") - mu) / sd, 2)
    scores = []
    for i in range(4):
        den = sum(abs(x["w"][i]) for x in rows)
        scores.append(round(sum(x["w"][i] * x["z"] for x in rows) / den, 3))
    return rows, dict(scores=scores, best=scores.index(max(scores)))

def compute_econ(ip, un, yc, hy, cpi):
    def yoy(p, i=-1):
        return (p[i][1] / p[i - 12][1] - 1) * 100
    ind, votes = [], [0, 0, 0, 0]
    def add(name, val, v, why):
        ind.append(dict(name=name, val=val, v=v, why=why)); votes[v] += 1
    g = yoy(ip); gm = g - yoy(ip, -7)
    v = 3 if g < 0 else 0 if gm >= 1 else 1 if gm > -1 else 2
    add("산업생산 (전년비)", f"{g:.1f}% · 6개월 전보다 {gm:+.1f}%p", v, "마이너스=침체, 가속=초기, 보합=중간, 둔화=후기")
    u3 = sum(x[1] for x in un[-3:]) / 3
    du = u3 - min(x[1] for x in un[-12:]); d6 = un[-1][1] - un[-7][1]
    v = 3 if du >= 0.5 else 2 if du >= 0.2 else 0 if d6 <= -0.3 else 1
    add("실업률", f"{un[-1][1]:.1f}% · 12개월 저점 대비 {du:+.1f}%p", v, "저점 대비 급등=침체·후기, 하락 중=초기")
    y = yc[-1][1]
    v = 2 if y < 0.25 else 1 if y < 1.25 else 0
    add("장단기 금리차 (10Y-2Y)", f"{y:.2f}%p", v, "역전·평탄=후기, 정상=중간, 가파름=초기")
    h = hy[-1][1]; hc = h - hy[-64][1] if len(hy) > 64 else 0
    v = 3 if h > 6 else 0 if (hc <= -0.5 and h > 4) else 2 if h < 3.5 else 1
    add("하이일드 스프레드", f"{h:.2f}%p · 3개월 {hc:+.2f}%p", v, "급등=침체, 고점에서 하락=초기, 매우 낮음=후기")
    i1 = yoy(cpi); ic = i1 - yoy(cpi, -7)
    v = 2 if ic >= 0.3 else 0 if ic <= -0.3 else 1
    add("CPI (전년비)", f"{i1:.1f}% · 6개월 전보다 {ic:+.1f}%p", v, "상승 압력=후기, 둔화=초기, 보합=중간")
    sc = [round(x / len(ind) * 100) for x in votes]
    return dict(scores=sc, best=sc.index(max(sc)), ind=ind)

def main():
    today = dt.date.today()
    start = (today - dt.timedelta(days=900)).isoformat()
    sectors, market = compute_market(get_prices())
    econ = compute_econ(fred("INDPRO", start), fred("UNRATE", start), fred("T10Y2Y", start),
                        fred("BAMLH0A0HYM2", start), fred("CPIAUCSL", start))
    kst = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")
    json.dump(dict(updated=kst, phases=PH, sectors=sectors, market=market, econ=econ),
              open("cycle.json", "w", encoding="utf-8"), ensure_ascii=False)

if __name__ == "__main__":
    main()
