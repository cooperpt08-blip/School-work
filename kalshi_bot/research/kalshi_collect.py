"""Download Kalshi price histories for NBA/NFL game, spread, total and player-prop markets.

Markets settled after Kalshi's archive cutoff come 100-per-request from the live API; archived
ones are one request each (~1/s), so the archive is sampled: every game-winner event, and the
middle rung of each spread/total/prop ladder. Each record keeps the market's hourly candles
(bid, ask, volume, open interest) from listing until the event, so any snapshot can be taken later.

Output: research/data/kalshi_<SERIES>.jsonl.gz. Resumable.
"""
import gzip
import json
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from kalshi_bot import kalshi  # noqa: E402

OUT = Path(__file__).resolve().parent / "data"
OUT.mkdir(parents=True, exist_ok=True)
SERIES = [  # (series, max archived groups to sample)
    ("KXNBAGAME", 10**6), ("KXNFLGAME", 10**6),
    ("KXNBASPREAD", 700), ("KXNBATOTAL", 700), ("KXNFLSPREAD", 400), ("KXNFLTOTAL", 400),
    ("KXNBAPTS", 900), ("KXNBAREB", 700), ("KXNBAAST", 700), ("KXNBA3PT", 700),
    ("KXNFLRECYDS", 900), ("KXNFLRSHYDS", 700), ("KXNFLPASSYDS", 500),
]
KEEP = ("ticker", "event_ticker", "title", "subtitle", "yes_sub_title", "no_sub_title", "floor_strike", "cap_strike",
        "strike_type", "result", "open_time", "close_time", "occurrence_datetime", "expected_expiration_time",
        "rules_primary")


def group_key(series, ticker):
    # props: KXNBAPTS-<event>-<PLAYER><n>-<strike>  -> one group per player-game
    # spreads/totals: one group per event; game winners: one group per event
    parts = ticker.split("-")
    if series.endswith("GAME") or "SPREAD" in series or "TOTAL" in series:
        return parts[1]
    return "-".join(parts[1:3])


def strike(m):
    for k in ("floor_strike", "cap_strike"):
        if m.get(k) is not None:
            return float(m[k])
    mm = re.search(r"(\d+(?:\.\d+)?)$", m["ticker"])
    return float(mm.group(1)) if mm else 0.0


def list_markets(series):
    arch = list(kalshi.paged("/historical/markets", "markets", {"series_ticker": series, "limit": 1000}))
    recent = list(kalshi.settled_markets(series, time.time() - 120 * 86400, time.time()))
    return arch, recent


def pick(series, ms, cap):
    groups = {}
    for m in ms:
        if m.get("result") in ("yes", "no"):
            groups.setdefault(group_key(series, m["ticker"]), []).append(m)
    keys = sorted(groups)
    random.Random(series).shuffle(keys)
    out = []
    for k in keys[:cap]:
        g = sorted(groups[k], key=strike)
        out.append(g[len(g) // 2])  # middle rung of the ladder (game winners: one side)
    return out


def candles(m, archived):
    occ = kalshi.ts(m.get("occurrence_datetime") or m.get("expected_expiration_time"))
    opn = kalshi.ts(m.get("open_time"))
    if not occ or not opn:
        return None
    start, end = int(opn.timestamp()), int(occ.timestamp())
    start = max(start, end - 10 * 86400)
    path = (f"/historical/markets/{m['ticker']}/candlesticks" if archived else
            f"/series/{m['event_ticker'].split('-')[0]}/markets/{m['ticker']}/candlesticks")
    try:
        d = kalshi.get(path, {"start_ts": start, "end_ts": end, "period_interval": 60})
    except Exception:  # noqa: BLE001
        return None
    return _compact(d.get("candlesticks") or [])


def _compact(cs):
    out = []
    for c in cs:
        b, a = c.get("yes_bid") or {}, c.get("yes_ask") or {}
        out.append([c.get("end_period_ts"), kalshi.dollars(b.get("close_dollars", b.get("close"))),
                    kalshi.dollars(a.get("close_dollars", a.get("close"))),
                    kalshi.dollars(c.get("volume_fp", c.get("volume"))), kalshi.dollars(c.get("open_interest_fp", c.get("open_interest")))])
    return out


def batch_candles(ms):
    """Live API: up to 100 markets per request."""
    out = {}
    ms = sorted(ms, key=lambda m: m.get("occurrence_datetime") or "")
    for i in range(0, len(ms), 100):
        chunk = ms[i:i + 100]
        occs = [kalshi.ts(m.get("occurrence_datetime") or m.get("expected_expiration_time")) for m in chunk]
        end = int(max(o.timestamp() for o in occs if o))
        start = int(min(o.timestamp() for o in occs if o)) - 4 * 86400
        d = None
        for attempt in range(5):  # never silently drop a chunk
            try:
                d = kalshi.get("/markets/candlesticks", {"market_tickers": ",".join(m["ticker"] for m in chunk),
                                                         "start_ts": start, "end_ts": end, "period_interval": 60})
                break
            except Exception as e:  # noqa: BLE001
                print(f"    batch retry {attempt + 1}: {str(e)[:80]}", flush=True)
                time.sleep(20 * (attempt + 1))
        if d is None:
            continue
        by = {m["ticker"]: m for m in chunk}
        for row in d.get("markets") or []:
            t = row.get("market_ticker")
            occ = kalshi.ts(by[t].get("occurrence_datetime") or by[t].get("expected_expiration_time")).timestamp()
            out[t] = [c for c in _compact(row.get("candlesticks") or []) if c[0] <= occ]
    return out


def collect(series, cap, recent_only=False):
    f = OUT / f"kalshi_{series}.jsonl.gz"
    have = set()
    if f.exists():
        with gzip.open(f, "rt") as fh:
            have = {json.loads(line)["ticker"] for line in fh}
    if recent_only:
        arch, recent = [], list(kalshi.settled_markets(series, time.time() - 120 * 86400, time.time()))
    else:
        arch, recent = list_markets(series)
    recent_pick = [m for m in pick(series, recent, 10**6) if m["ticker"] not in have]
    arch_pick = [] if recent_only else [m for m in pick(series, arch, cap) if m["ticker"] not in have]
    print(f"{series}: {len(recent_pick)} recent (batched) + {len(arch_pick)} archived to fetch", flush=True)
    with gzip.open(f, "at") as fh:
        for t, cs in batch_candles(recent_pick).items():
            m = next(x for x in recent_pick if x["ticker"] == t)
            fh.write(json.dumps({**{k: m.get(k) for k in KEEP}, "candles": cs}) + "\n")
        fh.flush()
        kalshi.MIN_GAP = 1.05  # archive rate limit
        for i, m in enumerate(arch_pick, 1):
            cs = candles(m, archived=True)
            if cs is not None:
                fh.write(json.dumps({**{k: m.get(k) for k in KEEP}, "candles": cs}) + "\n")
            if i % 100 == 0:
                fh.flush()
                print(f"  {series} archive {i}/{len(arch_pick)}", flush=True)
        kalshi.MIN_GAP = 0.22


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    recent_only = "--recent-only" in sys.argv
    for s, cap in SERIES:
        if not args or s in args:
            collect(s, cap, recent_only=recent_only)
