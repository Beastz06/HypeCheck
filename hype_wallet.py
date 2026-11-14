"""Hype vs. Wallet - data + scoring functions.
pip install requests yfinance anthropic pandas
Env: YOUTUBE_API_KEY (optional), ANTHROPIC_API_KEY, FLASHPOINT_TOKEN
NOTE: written without network access - run each function once and check the output shape.
"""
import os, json, math, statistics, datetime as dt
import requests

UA = {"User-Agent": "hype-vs-wallet-hackathon/0.1 (student project)"}
TODAY = dt.date.today()
CAP = 3.0  # trend ratio that maps to a Hype score of 100


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
    items = requests.get(url, headers=UA, timeout=30).json()["items"]
    views = [i["views"] for i in items]
    return _ratio(views[-recent_days:], views[:-recent_days]), views


def gdelt_ratio(query, end=TODAY, recent_days=30, base_days=365):
    """GDELT news volume (share of all coverage) over time."""
    start = end - dt.timedelta(days=recent_days + base_days)
    params = {"query": query, "mode": "timelinevol", "format": "json",
              "startdatetime": f"{start:%Y%m%d}000000", "enddatetime": f"{end:%Y%m%d}235959"}
    r = requests.get("https://api.gdeltproject.org/api/v2/doc/doc", params=params, headers=UA, timeout=60)
    vals = [d["value"] for d in r.json()["timeline"][0]["data"]]
    n = max(1, round(len(vals) * recent_days / (recent_days + base_days)))
    return _ratio(vals[-n:], vals[:-n]), vals


def gdelt_headlines(query, n=50):
    """Recent headlines, used for the positive/negative split."""
    params = {"query": f"{query} sourcelang:english", "mode": "artlist", "format": "json",
              "maxrecords": n, "timespan": "1m", "sort": "datedesc"}
    r = requests.get("https://api.gdeltproject.org/api/v2/doc/doc", params=params, headers=UA, timeout=60)
    return [a["title"] for a in r.json().get("articles", [])]


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
            "publishedAfter": lo.isoformat() + "Z", "publishedBefore": hi.isoformat() + "Z", "key": key}).json()
        ids = ",".join(i["id"]["videoId"] for i in s.get("items", []))
        if not ids:
            totals.append(0); continue
        v = requests.get("https://www.googleapis.com/youtube/v3/videos",
                         params={"part": "statistics", "id": ids, "key": key}).json()
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
    r = requests.get(url, headers={"Authorization": f"Bearer {os.environ['FLASHPOINT_TOKEN']}"}, timeout=60)
    r.raise_for_status()
    return r.json()

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


if __name__ == "__main__":
    for name, article, query, ticker in [
        ("On", "On_(company)", '"On Running"', "ONON"),      # check the Wikipedia article title
        ("Nike", "Nike,_Inc.", '"Nike running"', "NKE"),
    ]:
        w, _ = wiki_ratio(article); g, _ = gdelt_ratio(query); y, _ = youtube_ratio(query + " shoes")
        print(name, {"wiki": w, "gdelt": g, "youtube": y, "hype": hype_score([w, g, y]), "market": market(ticker)})
    # Backtest: GameStop, window ending 31 Jan 2021
    e = dt.date(2021, 1, 31)
    print("GME", wiki_ratio("GameStop", end=e)[0], gdelt_ratio("GameStop", end=e)[0], market("GME", end=e))
