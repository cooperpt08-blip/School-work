"""Small client for Kalshi's public (no-login) market-data API."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = "https://api.elections.kalshi.com/trade-api/v2"
_last_call = [0.0]
MIN_GAP = 0.22  # seconds between calls; Kalshi returns 429 if we go faster


def get(path, params=None, tries=7):
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    for i in range(tries):
        wait = MIN_GAP - (time.time() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "kalshi-picks-bot", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(min(30, 2 ** i))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(min(30, 2 ** i))
    raise RuntimeError(f"Kalshi API kept failing: {url}")


def paged(path, key, params):
    cursor = None
    while True:
        p = dict(params)
        if cursor:
            p["cursor"] = cursor
        d = get(path, p)
        yield from d.get(key) or []
        cursor = d.get("cursor")
        if not cursor:
            return


def dollars(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def ts(s):
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def sports_series():
    """ticker -> series info (title, tags) for every Kalshi sports series."""
    return {s["ticker"]: s for s in paged("/series", "series", {"category": "Sports"})}


def open_sports_events():
    for e in paged("/events", "events", {"status": "open", "limit": 200, "with_nested_markets": "true"}):
        if e.get("category") == "Sports":
            yield e


def markets_by_ticker(tickers):
    out = {}
    tickers = list(tickers)
    for i in range(0, len(tickers), 100):
        chunk = tickers[i:i + 100]
        d = get("/markets", {"tickers": ",".join(chunk), "limit": 1000})
        for m in d.get("markets") or []:
            out[m["ticker"]] = m
    return out


def settled_markets(series_ticker, min_close_ts, max_close_ts):
    # Kalshi settles ~100k markets an hour across all categories, so always filter by series.
    yield from paged("/markets", "markets", {"series_ticker": series_ticker, "status": "settled", "limit": 1000,
                                             "min_close_ts": int(min_close_ts), "max_close_ts": int(max_close_ts)})


def candle_quotes(tickers, at_ts, window_hours=12):
    """For each ticker: (yes_bid, yes_ask) from the last hourly candle ending at or before at_ts."""
    out = {}
    tickers = list(tickers)
    for i in range(0, len(tickers), 100):
        chunk = tickers[i:i + 100]
        d = get("/markets/candlesticks", {"market_tickers": ",".join(chunk), "start_ts": int(at_ts - window_hours * 3600),
                                          "end_ts": int(at_ts), "period_interval": 60})
        for m in d.get("markets") or []:
            best = None
            for c in m.get("candlesticks") or []:
                if c.get("end_period_ts", 0) <= at_ts:
                    bid = dollars((c.get("yes_bid") or {}).get("close_dollars"))
                    ask = dollars((c.get("yes_ask") or {}).get("close_dollars"))
                    if bid is not None and ask is not None:
                        best = (bid, ask)
            if best and m.get("market_ticker"):
                out[m["market_ticker"]] = best
    return out
