"""Hype vs. Wallet - data + scoring functions.
pip install requests yfinance anthropic pandas python-dotenv
Env: YOUTUBE_API_KEY (optional), ANTHROPIC_API_KEY, FLASHPOINT_TOKEN
"""
import os, json, re, statistics, time, datetime as dt
import requests
from dotenv import load_dotenv

load_dotenv()

UA = {"User-Agent": "hype-vs-wallet-hackathon/0.1 (student project)"}
TODAY = dt.date.today()
CAP = 3.0  # trend ratio that maps to a Hype score of 100
HTTP_TIMEOUT = 20

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
os.makedirs(CACHE_DIR, exist_ok=True)


def _slug(s):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(s)).strip("_")[:120] or "x"


def _cache(name, payload):
    path = os.path.join(CACHE_DIR, f"{_slug(name)}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        print(f"[cache] failed to write {path}: {e}")
    return payload


def _ratio(recent, baseline):
    """mean(recent) / median(baseline); 1.0 means 'no change'."""
    if not recent or not baseline:
        return None
    base = statistics.median(baseline)
    return (sum(recent) / len(recent)) / base if base else None


# ---------- HYPE ----------
def wiki_ratio(article, end=TODAY, recent_days=30, base_days=365):
    """Wikipedia daily pageviews: last 30 days vs. median of the prior 12 months."""
    start = end - dt.timedelta(days=recent_days + base_days)
    url = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
           f"en.wikipedia/all-access/user/{article}/daily/{start:%Y%m%d}/{end:%Y%m%d}")
    r = requests.get(url, headers=UA, timeout=HTTP_TIMEOUT)
    try:
        body = r.json()
    except ValueError:
        print(f"[wiki] non-JSON response for {article!r}: {r.text[:300]}")
        _cache(f"wiki_{article}_raw", {"status": r.status_code, "text": r.text[:2000]})
        return None, []
    _cache(f"wiki_{article}", body)
    if not isinstance(body, dict) or "items" not in body:
        print(f"[wiki] unexpected shape for {article!r}: {json.dumps(body)[:400]}")
        return None, []
    items = body["items"]
    views = [i.get("views", 0) for i in items]
    if len(views) <= recent_days:
        return None, views
    return _ratio(views[-recent_days:], views[:-recent_days]), views


def gdelt_headlines(query, n=50):
    """Recent English headlines (last month). No retries; returns [] on any failure."""
    params = {"query": f"{query} sourcelang:english", "mode": "artlist", "format": "json",
              "maxrecords": n, "timespan": "1m", "sort": "datedesc"}
    try:
        r = requests.get("https://api.gdeltproject.org/api/v2/doc/doc",
                         params=params, headers=UA, timeout=HTTP_TIMEOUT)
    except requests.RequestException as e:
        print(f"[gdelt_headlines] request failed for {query!r}: {e}")
        return []
    try:
        body = r.json()
    except ValueError:
        print(f"[gdelt_headlines] non-JSON response for {query!r}: {r.text[:200]}")
        _cache(f"gdelt_headlines_{query}_raw", {"status": r.status_code, "text": r.text[:2000]})
        return []
    _cache(f"gdelt_headlines_{query}", body)
    articles = body.get("articles", []) if isinstance(body, dict) else []
    return [a.get("title", "") for a in articles]


def youtube_ratio(query, end=TODAY, windows=4):
    """Views on the top 25 videos published in the last 30 days vs. earlier 30-day windows.
    Costs ~100 quota units per window. Returns None if no API key."""
    key = os.getenv("YOUTUBE_API_KEY")
    if not key:
        return None, []
    totals = []
    for w in range(windows):
        hi = dt.datetime.combine(end - dt.timedelta(days=30 * w), dt.time())
        lo = hi - dt.timedelta(days=30)
        s = requests.get("https://www.googleapis.com/youtube/v3/search", params={
            "part": "id", "q": query, "type": "video", "order": "viewCount", "maxResults": 25,
            "publishedAfter": lo.isoformat() + "Z", "publishedBefore": hi.isoformat() + "Z", "key": key},
            timeout=HTTP_TIMEOUT).json()
        _cache(f"youtube_search_{query}_w{w}", s)
        ids = ",".join(i["id"]["videoId"] for i in s.get("items", []))
        if not ids:
            totals.append(0); continue
        v = requests.get("https://www.googleapis.com/youtube/v3/videos",
                         params={"part": "statistics", "id": ids, "key": key},
                         timeout=HTTP_TIMEOUT).json()
        _cache(f"youtube_videos_{query}_w{w}", v)
        totals.append(sum(int(i["statistics"].get("viewCount", 0)) for i in v.get("items", [])))
    return _ratio(totals[:1], totals[1:]), totals


def hype_score(ratios):
    """Average the available trend ratios, map 1.0 -> 0 and CAP -> 100."""
    rs = [r for r in ratios if r]
    if not rs:
        return None
    avg = sum(rs) / len(rs)
    return round(max(0, min(1, (avg - 1) / (CAP - 1))) * 100)


def positive_share(product, headlines, model=os.getenv("MODEL", "claude-sonnet-5-5")):
    """Claude labels each headline's attitude toward the product."""
    import anthropic
    prompt = (f"For each headline, label the attitude toward {product} as positive, negative or neutral. "
              "Return only a JSON list of labels, one per headline, in order.\n\n" +
              "\n".join(f"{i+1}. {h}" for i, h in enumerate(headlines)))
    msg = anthropic.Anthropic().messages.create(model=model, max_tokens=2000,
                                                messages=[{"role": "user", "content": prompt}])
    text = msg.content[0].text
    labels = json.loads(text[text.index("["): text.rindex("]") + 1])
    pos, neg = labels.count("positive"), labels.count("negative")
    return {"positive": pos, "negative": neg, "neutral": len(labels) - pos - neg,
            "positive_share": round(pos / max(1, pos + neg), 2)}


# ---------- MARKET ----------
def market(ticker, end=TODAY, recent_days=30):
    import yfinance as yf
    df = yf.download(ticker, start=end - dt.timedelta(days=400), end=end + dt.timedelta(days=1),
                     progress=False, auto_adjust=True)
    try:
        flat = df.copy()
        if hasattr(flat.columns, "to_flat_index"):
            flat.columns = ["_".join(str(x) for x in c if x) if isinstance(c, tuple) else str(c)
                            for c in flat.columns.to_flat_index()]
        _cache(f"market_{ticker}_{end}", flat.reset_index().to_dict(orient="list"))
    except Exception as e:
        print(f"[cache] market serialize failed for {ticker}: {e}")
    close, vol = df["Close"].squeeze(), df["Volume"].squeeze()
    n = 21  # ~30 calendar days of trading
    price_change = float(close.iloc[-1] / close.iloc[-n] - 1)
    volume_ratio = float(vol.iloc[-n:].mean() / vol.iloc[:-n].median())
    score = round(max(0, min(100, 50 + 100 * price_change)))
    return {"price_change": round(price_change, 3), "volume_ratio": round(volume_ratio, 2), "score": score}


# ---------- WALLET (Flashpoint) ----------
FP = "https://api.flashpoint.ai/api/v1"

def fp_frequencies(survey_id, label=None):
    """Raw frequencies from Flashpoint. Print once to see the shape, then pull the counts."""
    url = f"{FP}/surveys/{survey_id}/analytics/frequencies" + (f"/{label}" if label else "")
    token = re.sub(r"[^\x21-\x7e]", "", os.environ["FLASHPOINT_TOKEN"])  # drop pasted invisible chars
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    body = r.json()
    _cache(f"fp_freq_{survey_id}_{label or 'all'}", body)
    return body

def wallet_score(definitely, probably, total):
    """Discounted purchase intent at the real price. Max possible is 80."""
    return round(100 * (0.8 * definitely + 0.3 * probably) / max(1, total))


# ---------- VERDICT ----------
def verdict(product, control, threshold=15):
    """Each arg: {'hype': int, 'wallet': int}. Compares the product's gap with the control's."""
    gap_p, gap_c = product["hype"] - product["wallet"], control["hype"] - control["wallet"]
    diff = gap_p - gap_c
    label = "OVERHYPED" if diff > threshold else "UNDER-THE-RADAR" if diff < -threshold else "IN LINE"
    return {"product_gap": gap_p, "control_gap": gap_c, "difference": diff, "verdict": label}


def _timed(label, fn, *args, **kwargs):
    t0 = time.time()
    try:
        out = fn(*args, **kwargs)
    except Exception as e:
        print(f"[{label}] FAILED after {time.time()-t0:.1f}s: {e}")
        return None
    print(f"[{label}] {time.time()-t0:.1f}s")
    return out


if __name__ == "__main__":
    rows = []
    for name, article, query, ticker in [
        ("On", "On_(company)", '"On Running"', "ONON"),
        ("Nike", "Nike,_Inc.", '"Nike running"', "NKE"),
    ]:
        print(f"\n--- {name} ---")
        wres = _timed(f"{name} wiki", wiki_ratio, article)
        w = wres[0] if wres else None
        yres = _timed(f"{name} youtube", youtube_ratio, query + " shoes")
        y = yres[0] if yres else None
        m = _timed(f"{name} market", market, ticker)
        hdl = _timed(f"{name} gdelt_headlines", gdelt_headlines, query)
        h = hype_score([w, y])
        rows.append((name, w, y, h, m, len(hdl) if hdl else 0))
        print(name, {"wiki": w, "youtube": y, "hype": h, "market": m, "headlines": len(hdl) if hdl else 0})

    # Backtest: GameStop, window ending 31 Jan 2021 (Hype = Wikipedia only)
    print("\n--- GameStop backtest (ending 2021-01-31) ---")
    e = dt.date(2021, 1, 31)
    gme_wres = _timed("GME wiki", wiki_ratio, "GameStop", end=e)
    gme_wiki = gme_wres[0] if gme_wres else None
    gme_market = _timed("GME market", market, "GME", end=e)
    gme_hype = hype_score([gme_wiki])
    print("GME", {"wiki": gme_wiki, "hype": gme_hype, "market": gme_market})

    # Final summary table
    def fmt(v, nd=2):
        return "n/a" if v is None else f"{v:.{nd}f}" if isinstance(v, float) else str(v)

    print("\n=== SUMMARY ===")
    print(f"{'Product':<10} {'Wiki':>8} {'YouTube':>8} {'Hype':>6} {'Market':>8}")
    for name, w, y, h, m, _n in rows:
        mscore = m['score'] if m else None
        print(f"{name:<10} {fmt(w):>8} {fmt(y):>8} {fmt(h):>6} {fmt(mscore):>8}")
    gmescore = gme_market['score'] if gme_market else None
    print(f"{'GameStop':<10} {fmt(gme_wiki):>8} {'n/a':>8} {fmt(gme_hype):>6} {fmt(gmescore):>8}")

    if gme_market:
        print(f"\nGameStop backtest detail: price_change={gme_market['price_change']}, "
              f"volume_ratio={gme_market['volume_ratio']}, market_score={gme_market['score']}")
