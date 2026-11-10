"""Seed the learner with already-settled Kalshi sports markets and the prices they had pre-game."""
import random
import re
import time
from datetime import timedelta

from . import config, kalshi, store
from .ratings import Matcher


def backfill(days=21, per_series=400, series=None, log=print):
    """IMPORTANT: never choose which settled markets to learn from using anything measured after the
    game started (final volume, last price...). Final volume is higher for props that hit, because
    they trade heavily as they cash - selecting on it teaches the model a fake edge. So: sample at
    random, and judge liquidity only from open interest at the pre-game snapshot time."""
    now = time.time()
    series_info = kalshi.sports_series()
    have = {r["ticker"] for r in store.load_snapshots()}
    # Only series that are live right now (have open events) - thousands of listed series are dormant.
    active = sorted(set(series or [e["series_ticker"] for e in kalshi.open_sports_events()]) & set(series_info))
    log(f"  listing settled markets from the last {days} days in {len(active)} active sports series")
    picked = {}
    for n, s in enumerate(active, 1):
        for m in kalshi.settled_markets(s, now - days * 86400, now):
            if m["ticker"] in have or m.get("result") not in ("yes", "no"):
                continue
            occ = kalshi.ts(m.get("occurrence_datetime") or m.get("expected_expiration_time"))
            if occ:
                picked.setdefault(s, []).append((m, occ))
        if n % 100 == 0:
            log(f"    {n}/{len(active)} series listed")
    todo = []
    for s, ms in picked.items():
        random.Random(s).shuffle(ms)
        todo.extend((s, m, occ) for m, occ in ms[:per_series])
    log(f"  {len(todo)} settled markets across {len(picked)} series; fetching pre-game prices")
    todo.sort(key=lambda t: t[2])
    matcher, rows, results = Matcher(), [], store.load_results()
    for i in range(0, len(todo), 100):
        chunk = todo[i:i + 100]
        at = {m["ticker"]: (occ - timedelta(hours=config.BACKFILL_SNAPSHOT_HOURS)).timestamp() for _, m, occ in chunk}
        quotes = {}
        # one candle request per chunk, window covering every market's snapshot time
        lo, hi = min(at.values()), max(at.values())
        spans = [(lo, hi)] if hi - lo <= 4 * 86400 else [(a, a) for a in at.values()]
        for s_lo, s_hi in spans:  # keep requests small if a chunk spans many days
            got = _candles_window([t for t, a in at.items() if s_lo <= a <= s_hi], s_lo - 12 * 3600, s_hi)
            for t, cs in got.items():
                best = None
                for end_ts, bid, ask, oi in cs:
                    if end_ts <= at[t]:
                        best = (bid, ask, oi)
                if best:
                    quotes[t] = best
        for series, m, occ in chunk:
            q = quotes.get(m["ticker"])
            if not q:
                continue
            bid, ask, oi = q
            if bid is None or ask is None or not (0 < bid <= ask < 1) or ask - bid > config.MAX_SPREAD_LOG:
                continue
            if bid < config.MIN_PRICE or ask > config.MAX_PRICE or (oi or 0) < config.MIN_LIQUIDITY / 2:
                continue  # same filters as live scanning, measured before the game
            tag = ((series_info.get(series) or {}).get("tags") or ["Other"])[0]
            p_elo, _ = matcher.game_prob(series, m["event_ticker"], _event_title(m), m.get("yes_sub_title"))
            snap_at = occ - timedelta(hours=config.BACKFILL_SNAPSHOT_HOURS)
            rows.append({"snap_ts": snap_at.isoformat(timespec="seconds"), "source": "backfill", "ticker": m["ticker"],
                         "event_ticker": m["event_ticker"], "series": series, "tag": tag, "occurrence": occ.isoformat(),
                         "yes_bid": bid, "yes_ask": ask, "p_elo": "" if p_elo is None else round(p_elo, 4),
                         "event_title": _event_title(m), "market_title": m.get("title", "")})
            results[m["ticker"]] = m["result"]
        if (i // 100) % 20 == 0:
            log(f"    {min(i + 100, len(todo))}/{len(todo)}")
    store.append_snapshots(rows)
    store.save_results(results)
    log(f"  backfilled {len(rows)} rows ({sum(1 for r in rows if r['p_elo'] != '')} with team ratings)")


def _event_title(m):
    # settled-market listings don't include the event title; game markets read "Will X win the X vs Y ..."
    # The rules text names both teams: "If Cleveland wins the Cleveland vs Charlotte Pro Basketball game ..."
    r = m.get("rules_primary") or ""
    mm = re.search(r"the (.+? (?:vs\.?|at) .+?) (?:Pro|College|Women|Men|professional|game|match)", r)
    return mm.group(1) if mm else ""


def _candles_window(tickers, start, end):
    d = kalshi.get("/markets/candlesticks", {"market_tickers": ",".join(tickers), "start_ts": int(start),
                                              "end_ts": int(end), "period_interval": 60})
    out = {}
    for m in d.get("markets") or []:
        cs = []
        for c in m.get("candlesticks") or []:
            cs.append((c.get("end_period_ts", 0), kalshi.dollars((c.get("yes_bid") or {}).get("close_dollars")),
                       kalshi.dollars((c.get("yes_ask") or {}).get("close_dollars")),
                       kalshi.dollars(c.get("open_interest_fp"))))
        out[m.get("market_ticker")] = cs
    return out
