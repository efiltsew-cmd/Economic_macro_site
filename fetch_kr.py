import json, re, html, urllib.request, datetime as dt

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
errors = []
POOL = {
    "반도체": [("005930", "삼성전자"), ("000660", "SK하이닉스"), ("042700", "한미반도체"), ("058470", "리노공업"), ("000990", "DB하이텍"), ("039030", "이오테크닉스"), ("403870", "HPSP"), ("036930", "주성엔지니어링"), ("240810", "원익IPS"), ("089030", "테크윙")],
    "원자력": [("034020", "두산에너빌리티"), ("052690", "한전기술"), ("051600", "한전KPS"), ("032820", "우리기술"), ("094820", "일진파워"), ("083650", "비에이치아이"), ("006910", "보성파워텍"), ("105840", "우진"), ("000720", "현대건설"), ("047040", "대우건설")],
    "로봇": [("454910", "두산로보틱스"), ("277810", "레인보우로보틱스"), ("108490", "로보티즈"), ("011210", "현대위아"), ("389500", "에스비비테크"), ("090710", "휴림로봇"), ("388720", "유일로보틱스"), ("466100", "클로봇"), ("475400", "씨메스"), ("348340", "뉴로메카")],
    "방산": [("012450", "한화에어로스페이스"), ("064350", "현대로템"), ("079550", "LIG넥스원"), ("047810", "한국항공우주"), ("272210", "한화시스템"), ("103140", "풍산"), ("065450", "빅텍"), ("013810", "스페코"), ("099320", "쎄트렉아이"), ("064960", "SNT모티브")],
    "조선": [("009540", "HD한국조선해양"), ("010140", "삼성중공업"), ("042660", "한화오션"), ("329180", "HD현대중공업"), ("010620", "HD현대미포"), ("017960", "한국카본"), ("443060", "HD현대마린솔루션"), ("014620", "성광벤드"), ("023160", "태광"), ("033500", "동성화인텍")],
    "AI": [("035420", "NAVER"), ("035720", "카카오"), ("018260", "삼성SDS"), ("012510", "더존비즈온"), ("304100", "솔트룩스"), ("402030", "코난테크놀로지"), ("047560", "이스트소프트"), ("377480", "마음AI"), ("030520", "한글과컴퓨터"), ("041020", "폴라리스오피스")],
    "항공우주": [("047810", "한국항공우주"), ("012450", "한화에어로스페이스"), ("099320", "쎄트렉아이"), ("189300", "인텔리안테크"), ("079550", "LIG넥스원"), ("274090", "켄코아에어로스페이스"), ("211270", "AP위성"), ("272210", "한화시스템"), ("003490", "대한항공"), ("089590", "제주항공")],
    "2차전지": [("373220", "LG에너지솔루션"), ("006400", "삼성SDI"), ("247540", "에코프로비엠"), ("086520", "에코프로"), ("005490", "POSCO홀딩스"), ("003670", "포스코퓨처엠"), ("066970", "엘앤에프"), ("096770", "SK이노베이션"), ("348370", "엔켐"), ("005070", "코스모신소재")],
}

def page(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode("euc-kr", "ignore")

def table_rows(h):
    out = []
    for tr in re.findall(r"(?s)<tr[^>]*>(.*?)</tr>", h):
        out.append([re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", c))).strip() for c in re.findall(r"(?s)<t[dh][^>]*>(.*?)</t[dh]>", tr)])
    return out

def num(s):
    s = s.replace(",", "").replace("+", "").strip()
    return float(s) if re.fullmatch(r"-?\d+(\.\d+)?", s) else None

def date_of(s):
    m = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{2})", s.strip())
    return f"20{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None

def fetch_flow(kind, sosok, pages=6):
    today = dt.date.today().strftime("%Y%m%d"); res = {}; scale = 1.0
    for p in range(1, pages + 1):
        h = page(f"https://finance.naver.com/sise/{kind}.naver?bizdate={today}&sosok={sosok}&page={p}")
        m = re.search(r"단위\s*[:：]?\s*([가-힣]+)", h)
        if m and "백만" in m.group(1):
            scale = 0.01
        rows = table_rows(h)
        head = next((r for r in rows if "개인" in r or "차익" in "".join(r)), [])
        for r in rows:
            d = date_of(r[0]) if r else None
            if d:
                res[d] = (r[1:], head)
    return res, scale

def investors(sosok):
    res, _ = fetch_flow("investorDealTrendDay", sosok)
    out = {}
    for d, (vals, head) in sorted(res.items()):
        names = [x for x in head if x != "날짜"]
        idx = {k: (names.index(k) if k in names else i) for i, k in enumerate(["개인", "외국인", "기관계"])}
        nums = [num(v) for v in vals]
        out[d] = {"개인": nums[idx["개인"]], "외국인": nums[idx["외국인"]], "기관": nums[idx["기관계"]]}
    return out

def programs(sosok):
    res, scale = fetch_flow("programDealTrendDay", sosok)
    out = {}
    for d, (vals, _) in sorted(res.items()):
        nums = [num(v) for v in vals]
        if len(nums) >= 9:
            out[d] = {"차익": nums[2] * scale if nums[2] is not None else None, "비차익": nums[5] * scale if nums[5] is not None else None, "전체": nums[8] * scale if nums[8] is not None else None}
    return out

def flow_json():
    res = {"updated": None}
    for k, code in (("kospi", "01"), ("kosdaq", "02")):
        try:
            inv = investors(code)
        except Exception as e:
            errors.append(f"{k} 투자자별: {e}"); continue
        try:
            prg = programs(code)
        except Exception as e:
            errors.append(f"{k} 프로그램: {e}"); prg = {}
        dates = sorted(inv)[-60:]
        m = {"dates": dates}
        for key in ("개인", "외국인", "기관"):
            m[key] = [inv[d][key] for d in dates]
        for key in ("차익", "비차익", "전체"):
            m[key] = [prg.get(d, {}).get(key) for d in dates]
        res[k] = m
    return res

def themes_json():
    import yfinance as yf
    import pandas as pd
    import sys
    sys.path.insert(0, ".")
    codes = sorted({c for v in POOL.values() for c, _ in v})
    tick = [c + s for c in codes for s in (".KS", ".KQ")]
    df = yf.download(tick, period="1y", auto_adjust=False, progress=False, threads=True)
    
    close, open_df, high_df, low_df, vol = df["Close"], df["Open"] if "Open" in df else close, df["High"] if "High" in df else close, df["Low"] if "Low" in df else close, df["Volume"]
    
    best = {}
    for c in codes:
        cand = [(close[c + s].dropna().size, c + s) for s in (".KS", ".KQ") if (c + s) in close]
        n, t = max(cand) if cand else (0, None)
        if t and n > 60:
            best[c] = t
    dates = [d.strftime("%Y-%m-%d") for d in close.index]
    def met(s):
        c = float(s.iloc[-1]); f = lambda n: round((c / float(s.iloc[-1 - n]) - 1) * 100, 2) if len(s) > n else None
        return dict(close=round(c, 2), chg=f(1), r5=f(5), r1m=f(21), r3m=f(63))
    out, px = [], {}
    for name, lst in POOL.items():
        rows = []
        for c, n in lst:
            t = best.get(c)
            if not t:
                continue
            s = close[t].dropna(); tv = float((close[t] * vol[t]).dropna().tail(20).mean()) / 1e8
            rows.append((tv, c, n, t, s))
        rows.sort(reverse=True); rows = rows[:10]
        if not rows:
            errors.append(f"{name}: 가격 데이터 없음"); continue
        stocks = []
        for tv, c, n, t, s in rows:
            o_s = open_df[t] if t in open_df else close[t]
            h_s = high_df[t] if t in high_df else close[t]
            l_s = low_df[t] if t in low_df else close[t]
            c_s = close[t]
            px[c] = [
                {
                    "time": d.strftime("%Y-%m-%d"),
                    "open": None if pd.isna(o) else round(float(o), 2),
                    "high": None if pd.isna(h) else round(float(h), 2),
                    "low": None if pd.isna(l) else round(float(l), 2),
                    "close": None if pd.isna(cc) else round(float(cc), 2)
                }
                for d, o, h, l, cc in zip(close.index, o_s, h_s, l_s, c_s) if not pd.isna(cc)
            ]
            stocks.append(dict(t=c, n=n, w=None, tv=round(tv, 1), **met(s)))
        norm = pd.concat([close[t].dropna() / close[t].dropna().iloc[0] * 100 for _, _, _, t, _ in rows], axis=1).mean(axis=1)
        key = "KR_" + name; ser = norm.reindex(close.index)
        px[key] = [
            {"time": d.strftime("%Y-%m-%d"), "open": round(v, 2), "high": round(v, 2), "low": round(v, 2), "close": round(v, 2)}
            for d, v in ser.items() if not pd.isna(v)
        ]
        out.append(dict(name=name, etf=key, src="auto", etf_row=dict(t=key, n=name + " TOP10 평균(지수화)", **met(norm.dropna())), stocks=stocks))
    return dict(asof=dates[-1], dates=dates, sectors=out, px=px)

def main():
    kst = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")
    try:
        f = flow_json(); f["updated"] = kst; f["errors"] = list(errors)
        json.dump(f, open("krflow.json", "w", encoding="utf-8"), ensure_ascii=False)
    except Exception as e:
        errors.append(f"수급: {e}")
    try:
        t = themes_json(); t["updated"] = kst; t["errors"] = list(errors)
        json.dump(t, open("krtheme.json", "w", encoding="utf-8"), ensure_ascii=False)
    except Exception as e:
        errors.append(f"테마: {e}")

if __name__ == "__main__":
    main()
