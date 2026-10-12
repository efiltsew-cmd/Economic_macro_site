import json, re, datetime as dt

SECT = [("IT", "XLK"), ("금융", "XLF"), ("임의소비재", "XLY"), ("커뮤니케이션 서비스", "XLC"), ("산업재", "XLI"), ("소재", "XLB"),
        ("에너지", "XLE"), ("헬스케어", "XLV"), ("필수소비재", "XLP"), ("유틸리티", "XLU"), ("부동산", "XLRE")]
# 자동 조회에 실패했을 때만 쓰는 고정 목록(시간이 지나면 순위가 어긋날 수 있음)
FIXED = {"XLK": ["NVDA", "MSFT", "AAPL", "AVGO", "ORCL"], "XLF": ["BRK-B", "JPM", "V", "MA", "BAC"],
         "XLY": ["AMZN", "TSLA", "HD", "MCD", "BKNG"], "XLC": ["META", "GOOGL", "NFLX", "TMUS", "DIS"],
         "XLI": ["GE", "CAT", "RTX", "UBER", "HON"], "XLB": ["LIN", "SHW", "FCX", "ECL", "APD"],
         "XLE": ["XOM", "CVX", "COP", "WMB", "EOG"], "XLV": ["LLY", "JNJ", "ABBV", "UNH", "MRK"],
         "XLP": ["WMT", "COST", "PG", "KO", "PM"], "XLU": ["NEE", "SO", "DUK", "CEG", "AEP"],
         "XLRE": ["PLD", "AMT", "WELL", "EQIX", "SPG"]}

def top5(etf):
    import yfinance as yf
    th = yf.Ticker(etf).funds_data.top_holdings
    out = []
    for sym, r in th.iterrows():
        s = str(sym).replace(".", "-").upper()
        if re.fullmatch(r"[A-Z]{1,5}(-[A-Z])?", s):
            w = r.get("Holding Percent")
            out.append((s, r.get("Name") or s, round(float(w) * 100, 2) if w == w and w is not None else None))
        if len(out) == 5:
            return out, "auto"
    raise ValueError("보유종목 5개를 찾지 못함")

def metrics(s):
    c = float(s.iloc[-1])
    f = lambda n: round((c / float(s.iloc[-1 - n]) - 1) * 100, 2) if len(s) > n else None
    return dict(close=round(c, 2), chg=f(1), r5=f(5), r1m=f(21), r3m=f(63))

def compose(top, df):
    import pandas as pd
    dates = [d.strftime("%Y-%m-%d") for d in df.index]
    out, used = [], set()
    for name, etf in SECT:
        rows, src = top[etf]
        stocks = []
        for t, n, w in rows:
            if t in df and df[t].dropna().size > 5:
                stocks.append(dict(t=t, n=n, w=w, **metrics(df[t].dropna()))); used.add(t)
        out.append(dict(name=name, etf=etf, src=src, etf_row=dict(t=etf, n=name + " 섹터 ETF", **metrics(df[etf].dropna())), stocks=stocks))
        used.add(etf)
    px = {t: [None if pd.isna(v) else round(float(v), 2) for v in df[t]] for t in sorted(used)}
    return dict(asof=dates[-1], dates=dates, sectors=out, px=px)

def main():
    import yfinance as yf
    top = {}
    for name, etf in SECT:
        try:
            top[etf] = top5(etf)
        except Exception as e:
            print("보유종목 조회 실패, 고정 목록 사용:", etf, e)
            top[etf] = ([(t, t, None) for t in FIXED[etf]], "fixed")
    tick = sorted({e for _, e in SECT} | {t for rows, _ in top.values() for t, _, _ in rows})
    df = yf.download(tick, period="1y", auto_adjust=False, progress=False)["Close"]
    res = compose(top, df)
    res["updated"] = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")
    json.dump(res, open("us.json", "w", encoding="utf-8"), ensure_ascii=False)

if __name__ == "__main__":
    main()
