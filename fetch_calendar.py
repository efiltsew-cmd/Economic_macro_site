import json, os, urllib.request, urllib.parse, datetime as dt

FRED = os.environ.get("FRED_API_KEY")
# (키, 이름, 그 릴리스에 속한 대표 FRED 시리즈) — 시리즈로 릴리스 번호를 찾아 발표 일정을 가져옴
ITEMS = [("cpi", "CPI (소비자물가)", "CPIAUCSL"), ("ppi", "PPI (생산자물가)", "PPIACO"), ("pce", "PCE 물가·소득지출", "PCEPI"),
         ("jobs", "고용 보고서 (비농업·실업률)", "PAYEMS"), ("retail", "소매판매", "RSAFS"), ("gdp", "GDP", "GDPC1")]
# 연준 공식 일정 기준 FOMC 결정 발표일(회의 둘째 날), 점도표(경제전망) 포함 여부. 2027년 일정은 확정되면 추가
FOMC = [("2026-10-28", False), ("2026-12-09", True)]
errors = []

def api(path, **kw):
    q = urllib.parse.urlencode(dict(api_key=FRED, file_type="json", **kw))
    return json.load(urllib.request.urlopen(f"https://api.stlouisfed.org/fred/{path}?{q}", timeout=30))

def release_dates(sid):
    rid = api("series/release", series_id=sid)["releases"][0]["id"]
    d = api("release/dates", release_id=rid, include_release_dates_with_no_data="true", sort_order="desc", limit=40)
    return sorted({x["date"] for x in d["release_dates"]})

def build(today):
    out = []
    for key, name, sid in ITEMS:
        try:
            ds = release_dates(sid)
        except Exception as e:
            errors.append(f"{name}: {e}"); continue
        t = today.isoformat(); horizon = (today + dt.timedelta(days=200)).isoformat()
        past = [d for d in ds if d <= t]; fut = [d for d in ds if t < d <= horizon]
        out.append(dict(key=key, name=name, prev=past[-1] if past else None, next=fut[0] if fut else None, upcoming=fut[:3]))
    return out

def main():
    today = dt.date.today()
    items = build(today)
    fomc = [dict(date=d, sep=s) for d, s in FOMC if d >= today.isoformat()]
    kst = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")
    json.dump(dict(updated=kst, items=items, fomc=dict(upcoming=fomc), errors=errors), open("calendar.json", "w", encoding="utf-8"), ensure_ascii=False)

if __name__ == "__main__":
    main()
