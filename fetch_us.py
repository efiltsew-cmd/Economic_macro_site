import json, re, datetime as dt

SECT = [("IT", "XLK"), ("금융", "XLF"), ("임의소비재", "XLY"), ("커뮤니케이션 서비스", "XLC"), ("산업재", "XLI"), ("소재", "XLB"),
        ("에너지", "XLE"), ("헬스케어", "XLV"), ("필수소비재", "XLP"), ("유틸리티", "XLU"), ("부동산", "XLRE")]

# 상위 10종목 고정 목록 (자동 조회 실패 시 대비)
FIXED = {
    "XLK": ["NVDA", "MSFT", "AAPL", "AVGO", "ORCL", "PLTR", "CRM", "AMD", "CSCO", "ACN"],
    "XLF": ["BRK-B", "JPM", "V", "MA", "BAC", "WFC", "C", "MS", "GS", "AXP"],
    "XLY": ["AMZN", "TSLA", "HD", "MCD", "BKNG", "LOW", "TJX", "SBUX", "NKE", "ABNB"],
    "XLC": ["META", "GOOGL", "NFLX", "TMUS", "DIS", "GOOG", "VZ", "CMCSA", "EA", "TTWO"],
    "XLI": ["GE", "CAT", "RTX", "UBER", "HON", "UNP", "DE", "ETN", "LMT", "GD"],
    "XLB": ["LIN", "SHW", "FCX", "ECL", "APD", "NEM", "DOW", "MLM", "VMC", "CF"],
    "XLE": ["XOM", "CVX", "COP", "WMB", "EOG", "SLB", "PXD", "MPC", "PSX", "VLO"],
    "XLV": ["LLY", "JNJ", "ABBV", "UNH", "MRK", "TMO", "ABT", "PFE", "DHR", "ISRG"],
    "XLP": ["WMT", "COST", "PG", "KO", "PM", "PEP", "MO", "MDLZ", "CL", "TGT"],
    "XLU": ["NEE", "SO", "DUK", "CEG", "AEP", "SRE", "PCG", "EXC", "XEL", "ED"],
    "XLRE": ["PLD", "AMT", "WELL", "EQIX", "SPG", "O", "PSA", "VICI", "CBRE", "CCI"]
}

def top10(etf):
    import yfinance as yf
    th = yf.Ticker(etf).funds_data.top_holdings
    out = []
    for sym, r in th.iterrows():
        s = str(sym).replace(".", "-").upper()
        if re.fullmatch(r"[A-Z]{1,5}(-[A-Z])?", s):
            w = r.get("Holding Percent")
            out.append((s, r.get("Name") or s, round(float(w) * 100, 2) if w == w and w is not None else None))
        if len(out) == 10:
            return out, "auto"
    if out:
        return out, "auto"
    raise ValueError("보유종목을 충분히 찾지 못함")

def metrics(s):
    c = float(s.iloc[-1])
    f = lambda n: round((c / float(s.iloc[-1 - n]) - 1) * 100, 2) if len(s) > n else None
    return dict(close=round(c, 2), chg=f(1), r5=f(5), r1m=f(21), r3m=f(63))

def compose(top, df_close, df_open, df_high, df_low):
    import pandas as pd
    dates = [d.strftime("%Y-%m-%d") for d in df_close.index]
    out, used = [], set()
    for name, etf in SECT:
        rows, src = top[etf]
        stocks = []
        for t, n, w in rows:
            if t in df_close and df_close[t].dropna().size > 5:
                stocks.append(dict(t=t, n=n, w=w, **metrics(df_close[t].dropna()))); used.add(t)
        out.append(dict(name=name, etf=etf, src=src, etf_row=dict(t=etf, n=name + " 섹터 ETF", **metrics(df_close[etf].dropna())), stocks=stocks))
        used.add(etf)
    
    # 캔들 차트를 위해 OHLC 데이터 모두 포함
    px = {}
    for t in sorted(used):
        if t in df_close:
            o_s = df_open[t] if t in df_open else df_close[t]
            h_s = df_high[t] if t in df_high else df_close[t]
            l_s = df_low[t] if t in df_low else df_close[t]
            c_s = df_close[t]
            px[t] = [
                {
                    "time": d.strftime("%Y-%m-%d"),
                    "open": None if pd.isna(o) else round(float(o), 2),
                    "high": None if pd.isna(h) else round(float(h), 2),
                    "low": None if pd.isna(l) else round(float(l), 2),
                    "close": None if pd.isna(c) else round(float(c), 2)
                }
                for d, o, h, l, c in zip(df_close.index, o_s, h_s, l_s, c_s) if not pd.isna(c)
            ]
    return dict(asof=dates[-1], dates=dates, sectors=out, px=px)

def main():
    import yfinance as yf
    top = {}
    for name, etf in SECT:
        try:
            top[etf] = top10(etf)
        except Exception as e:
            print("보유종목 조회 실패, 고정 목록 사용:", etf, e)
            top[etf] = ([(t, t, None) for t in FIXED[etf]], "fixed")
    tick = sorted({e for _, e in SECT} | {t for rows, _ in top.values() for t, _, _ in rows})
    df = yf.download(tick, period="1y", auto_adjust=False, progress=False)
    
    df_close = df["Close"]
    df_open = df["Open"] if "Open" in df else df_close
    df_high = df["High" if "High" in df else df_close
    df_low = df["Low"] if "Low" in df else df_close

    res = compose(top, df_close, df_open, df_high, df_low)
    res["updated"] = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")
    json.dump(res, open("us.json", "w", encoding="utf-8"), ensure_ascii=False)

if __name__ == "__main__":
    main()
