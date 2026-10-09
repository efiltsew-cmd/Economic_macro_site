import json, os, urllib.request, urllib.parse, datetime as dt

FRED, ECOS = os.environ.get("FRED_API_KEY"), os.environ.get("ECOS_API_KEY")
TG_TOKEN, TG_CHAT = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
SITE = os.environ.get("SITE_URL", "")
OUT = "data.json"
today = dt.date.today()

# (key, 이름, 단위, 소스, 코드, 변환, 일별여부)
SERIES = [
    ("us_rate", "미국 기준금리", "%", "fred", "FEDFUNDS", "raw", False),
    ("kr_rate", "한국 기준금리", "%", "ecos", ("722Y001", "M", "0101000"), "raw", False),
    ("usdkrw", "원/달러", "원", "ecos", ("731Y001", "D", "0000001"), "raw", True),
    ("jpykrw", "원/100엔", "원", "ecos", ("731Y001", "D", "0000002"), "raw", True),
    ("usdjpy", "달러/엔", "엔", "fred", "DEXJPUS", "raw", True),
    ("cpi", "CPI", "%", "fred", "CPIAUCSL", "yoy", False),
    ("core_cpi", "근원 CPI", "%", "fred", "CPILFESL", "yoy", False),
    ("ppi", "PPI", "%", "fred", "PPIACO", "yoy", False),
    ("pce", "PCE", "%", "fred", "PCEPI", "yoy", False),
    ("core_pce", "근원 PCE", "%", "fred", "PCEPILFE", "yoy", False),
    ("nfp", "비농업 고용 증감", "천 명", "fred", "PAYEMS", "diff", False),
    ("unemp", "실업률", "%", "fred", "UNRATE", "raw", False),
    ("retail", "소매판매", "%", "fred", "RSAFS", "mom", False),
    ("core_retail", "코어 소매판매(자동차 제외)", "%", "fred", "RSFSXMV", "mom", False),
    ("gdp", "GDP 성장률(연율)", "%", "fred", "A191RL1Q225SBEA", "raw", False),
    ("gdpnow", "GDPNow", "%", "fred", "GDPNOW", "raw", False),
]

def get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)

def fred(sid, start):
    q = urllib.parse.urlencode(dict(series_id=sid, api_key=FRED, file_type="json", observation_start=start))
    obs = get("https://api.stlouisfed.org/fred/series/observations?" + q)["observations"]
    return [(o["date"], float(o["value"])) for o in obs if o["value"] not in (".", "")]

def ecos(code, start, end):
    stat, cyc, item = code
    fmt = "%Y%m%d" if cyc == "D" else "%Y%m"
    url = f"https://ecos.bok.or.kr/api/StatisticSearch/{ECOS}/json/kr/1/10000/{stat}/{cyc}/{start.strftime(fmt)}/{end.strftime(fmt)}/{item}"
    rows = get(url)["StatisticSearch"]["row"]
    out = []
    for r in rows:
        t = r["TIME"]
        d = f"{t[:4]}-{t[4:6]}-{t[6:8]}" if len(t) == 8 else f"{t[:4]}-{t[4:6]}-01"
        out.append((d, float(r["DATA_VALUE"].replace(",", ""))))
    return out

def transform(p, kind):
    if kind == "raw":
        return p
    out = []
    for i, (d, v) in enumerate(p):
        if kind == "yoy" and i >= 12:
            out.append((d, (v / p[i - 12][1] - 1) * 100))
        elif kind == "mom" and i >= 1:
            out.append((d, (v / p[i - 1][1] - 1) * 100))
        elif kind == "diff" and i >= 1:
            out.append((d, v - p[i - 1][1]))
    return [(d, round(v, 2)) for d, v in out]

def send(text):
    if not (TG_TOKEN and TG_CHAT):
        return
    data = urllib.parse.urlencode(dict(chat_id=TG_CHAT, text=text)).encode()
    urllib.request.urlopen(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data, timeout=30)

try:
    old = json.load(open(OUT, encoding="utf-8"))["series"]
except Exception:
    old = {}

series, errors = {}, []
for key, name, unit, src, code, kind, daily in SERIES:
    try:
        start = today - dt.timedelta(days=800 if daily else 365 * 7)
        raw = fred(code, start.isoformat()) if src == "fred" else ecos(code, start, today)
        pts = transform(raw, kind)[-(520 if daily else 80):]
        if not pts:
            raise ValueError("데이터 없음")
        series[key] = dict(name=name, unit=unit, daily=daily, points=pts)
    except Exception as e:
        errors.append(f"{name}: {e}")
        if key in old:
            series[key] = old[key]  # 실패 시 이전 데이터 유지

kst = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")
json.dump(dict(updated=kst, series=series), open(OUT, "w", encoding="utf-8"), ensure_ascii=False)

def line(s):
    d, v = s["points"][-1]
    return f"• {s['name']}: {v:,.2f}{'%' if s['unit']=='%' else ' ' + s['unit']} ({d})"

changed = [s for k, s in series.items() if not s["daily"] and (k not in old or old[k]["points"][-1] != s["points"][-1])]
if changed or errors:
    msg = [f"📊 매크로 지표 업데이트 ({kst})"]
    msg += [line(s) for s in changed]
    fx = [line(s) for s in series.values() if s["daily"]]
    if fx:
        msg += ["", "환율"] + fx
    if errors:
        msg += ["", "⚠️ 수집 실패"] + errors
    if SITE:
        msg += ["", SITE]
    send("\n".join(msg))
