import json, os, re, html, urllib.request, urllib.parse, datetime as dt
import xml.etree.ElementTree as ET

FRED = os.environ.get("FRED_API_KEY")
UA = {"User-Agent": "Mozilla/5.0 (personal macro dashboard)"}
FEED = "https://www.federalreserve.gov/feeds/"
S, errors = {}, []
NAMES = {"powell": "Powell(의장)", "jefferson": "Jefferson(부의장)", "bowman": "Bowman(감독 부의장)", "waller": "Waller", "cook": "Cook", "barr": "Barr", "miran": "Miran", "kugler": "Kugler"}
# 문구 사전(문구, 가중치): 단어·문구 빈도로 매파/비둘기 성향을 점수화하는 단순 방식
HAWK = [("inflation remains elevated", 2), ("remains elevated", 1), ("somewhat elevated", 1), ("upside risks", 2), ("additional policy firming", 3),
        ("further tightening", 3), ("raise the target range", 3), ("sufficiently restrictive", 1), ("solid pace", 1), ("above 2 percent", 1),
        ("persistent", 1), ("price pressures", 1), ("strong labor market", 1)]
DOVE = [("lower the target range", 3), ("reduce the target range", 3), ("labor market has softened", 2), ("softening", 1), ("downside risks", 2),
        ("risks to employment", 2), ("has eased", 1), ("moderated", 1), ("slowed", 1), ("made progress", 1), ("more accommodative", 2),
        ("support the labor market", 1), ("weakness", 1), ("edged up", 1)]

def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode("utf-8", "ignore")

def fred(sid, start):
    q = urllib.parse.urlencode(dict(series_id=sid, api_key=FRED, file_type="json", observation_start=start))
    o = json.load(urllib.request.urlopen("https://api.stlouisfed.org/fred/series/observations?" + q, timeout=30))["observations"]
    return [(x["date"], float(x["value"])) for x in o if x["value"] not in (".", "")]

def put(key, name, unit, pts, n=900):
    if not pts:
        raise ValueError("데이터 없음")
    S[key] = dict(name=name, unit=unit, daily=True, points=[(d, round(v, 4)) for d, v in pts][-n:])

def attempt(label, fn):
    try:
        fn()
    except Exception as e:
        errors.append(f"{label}: {e}"); print("실패:", label, e)

def score(text):
    t = text.lower()
    hs = sum(w * min(t.count(p), 3) for p, w in HAWK); ds = sum(w * min(t.count(p), 3) for p, w in DOVE)
    return (round((hs - ds) / (hs + ds), 2) if hs + ds else 0.0), [p for p, _ in HAWK if p in t][:4], [p for p, _ in DOVE if p in t][:4]

def paras(url):
    h = re.sub(r"(?s)<(script|style).*?</\1>", "", get(url))
    ps = [html.unescape(re.sub(r"<[^>]+>", "", p)).strip() for p in re.findall(r"(?s)<p[^>]*>(.*?)</p>", h)]
    return [p for p in ps if len(p) > 40]

def sentences(ps):
    out = []
    for p in ps:
        if p.startswith("Voting for"):
            break
        out += [s.strip() for s in re.split(r"(?<=[.!?])\s+", p) if len(s.strip()) > 20]
    return out

def frac(x):
    m = re.fullmatch(r"(\d+)(?:-(\d+)/(\d+))?", x.strip())
    return None if not m else int(m.group(1)) + (int(m.group(2)) / int(m.group(3)) if m.group(2) else 0)

def decision(sents):
    for s in sents:
        if "target range for the federal funds rate" in s:
            a = re.search(r"to (raise|lower|reduce|maintain)", s)
            r = re.findall(r"(\d+(?:-\d+/\d+)?) to (\d+(?:-\d+/\d+)?) percent", s)
            lo, hi = (frac(r[-1][0]), frac(r[-1][1])) if r else (None, None)
            return {"raise": "인상", "lower": "인하", "reduce": "인하", "maintain": "동결"}.get(a.group(1) if a else "", "-"), (f"{lo:g}~{hi:g}" if lo is not None and hi is not None else None)
    return "-", None

def items(name, n):
    root = ET.fromstring(get(FEED + name).lstrip("\ufeff"))
    out = []
    for it in root.iter("item"):
        link = (it.findtext("link") or "").strip()
        m = re.search(r"(\d{8})[a-z]?\.htm", link)
        out.append(dict(title=(it.findtext("title") or "").strip(), url=link, date=f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}" if m else ""))
    return out[:n]

def fed():
    st = []
    for feed in ("press_monetary.xml", "press_all.xml"):
        try:
            st = [x for x in items(feed, 100) if "FOMC statement" in x["title"]][:4]
        except Exception as e:
            errors.append(f"{feed}: {e}"); continue
        if st:
            break
    if not st:
        raise ValueError("FOMC 성명 항목을 찾지 못함")
    res, texts = [], []
    for x in st:
        sents = sentences(paras(x["url"])); texts.append(sents)
        dec, rg = decision(sents); sc, h, d = score(" ".join(sents))
        res.append(dict(date=x["date"], title=x["title"], url=x["url"], decision=dec, range=rg, score=sc, hawk=h, dove=d))
    if len(texts) > 1:
        a, b = set(texts[0]), set(texts[1])
        res[0]["added"] = [s for s in texts[0] if s not in b][:6]; res[0]["removed"] = [s for s in texts[1] if s not in a][:6]
    sp = []
    for x in items("speeches_and_testimony.xml", 10):
        try:
            sc, h, d = score(" ".join(paras(x["url"])))
        except Exception as e:
            errors.append(f"연설 {x['url']}: {e}"); continue
        w = re.search(r"/([a-z]+)\d{8}", x["url"])
        sp.append(dict(date=x["date"], who=NAMES.get(w.group(1), w.group(1).title()) if w else "", title=x["title"], url=x["url"],
                       kind="증언" if "/testimony/" in x["url"] else "연설", score=sc, hawk=h, dove=d))
    return dict(statements=res, speeches=sp)

def yf_group(m):
    import yfinance as yf
    df = yf.download([v[0] for v in m.values()], period="4y", auto_adjust=False, progress=False)["Close"]
    if hasattr(df, "columns") is False:
        df = df.to_frame(list(m.values())[0][0])
    for k, (t, n, u) in m.items():
        attempt(n, lambda: put(k, n, u, [(i.strftime("%Y-%m-%d"), float(v)) for i, v in df[t].dropna().items()]))

def main():
    start = (dt.date.today() - dt.timedelta(days=1500)).isoformat()
    for k, n, sid in (("effr", "실효 연방기금금리", "DFF"), ("tb6m", "6개월물", "DTB6"), ("us1y", "1년물", "DGS1"), ("us2y", "2년물", "DGS2")):
        attempt(n, lambda: put(k, n, "%", fred(sid, start)))
    for g in ({"tlt": ("TLT", "미 장기국채 ETF(TLT)", "$"), "ief": ("IEF", "미 중기국채 ETF(IEF)", "$"), "shy": ("SHY", "미 단기국채 ETF(SHY)", "$")},
              {"kr3e": ("114260.KS", "KODEX 국고채3년", "원"), "kr10e": ("148070.KS", "KOSEF 국고채10년", "원"), "krf10e": ("152380.KS", "KODEX 국채선물10년", "원")}):
        attempt("가격 " + ",".join(g), lambda: yf_group(g))
    f = {"statements": [], "speeches": []}
    attempt("연준 발언", lambda: f.update(fed()))
    kst = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")
    json.dump(dict(updated=kst, series=S, fed=f, errors=errors), open("extra.json", "w", encoding="utf-8"), ensure_ascii=False)

if __name__ == "__main__":
    main()
