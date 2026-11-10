"""Scan every open Kalshi sports market, score both sides of each, and choose picks."""
from datetime import datetime, timedelta, timezone

from . import config, kalshi
from .model import Weights
from .ratings import Matcher, event_date
from .report import TZ


def game_key(event_ticker):
    # KXNBASPREAD-26NOV09CLECHA and KXNBAGAME-26NOV09CLECHA are the same game
    return event_ticker.split("-", 1)[1] if "-" in event_ticker else event_ticker


def scan(log=print, now=None):
    """-> (snapshot rows for learning, candidate bets)."""
    now = now or datetime.now(timezone.utc)
    lo = now + timedelta(hours=config.PREGAME_BUFFER_HOURS)
    hi = now + timedelta(hours=config.HORIZON_HOURS + config.PREGAME_BUFFER_HOURS)
    series_info = kalshi.sports_series()
    weights, matcher = Weights(), Matcher()
    snaps, cands = [], []
    n_events = n_markets = n_live = 0
    today_local = now.astimezone(TZ).date()
    for e in kalshi.open_sports_events():
        n_events += 1
        series = e.get("series_ticker", "")
        ev_day = event_date(e.get("event_ticker"))
        if ev_day and ev_day < today_local:
            continue  # yesterday's event still open = in progress or awaiting settlement; never bet those
        tags = (series_info.get(series) or {}).get("tags") or ["Other"]
        tag = tags[0]
        for m in e.get("markets") or []:
            if m.get("status") not in ("active", "open"):
                continue
            occ = kalshi.ts(m.get("occurrence_datetime") or m.get("expected_expiration_time"))
            if not occ or not (lo < occ < hi):
                continue
            bid, ask = kalshi.dollars(m.get("yes_bid_dollars")), kalshi.dollars(m.get("yes_ask_dollars"))
            if bid is None or ask is None or bid < config.MIN_PRICE or ask > config.MAX_PRICE:
                continue
            if ask - bid > config.MAX_SPREAD_LOG:
                continue
            liq = max(kalshi.dollars(m.get("open_interest_fp")) or 0, kalshi.dollars(m.get("volume_24h_fp")) or 0)
            if liq < config.MIN_LIQUIDITY:
                continue
            p_elo, game = matcher.game_prob(series, e.get("event_ticker"), e.get("title"), m.get("yes_sub_title"))
            if game and game["state"] != "pre":
                n_live += 1  # ESPN says it already started/finished: never recommend live games
                continue
            n_markets += 1
            snaps.append({"snap_ts": now.isoformat(timespec="seconds"), "source": "live", "ticker": m["ticker"],
                          "event_ticker": e.get("event_ticker", ""), "series": series, "tag": tag,
                          "occurrence": occ.isoformat(), "yes_bid": bid, "yes_ask": ask,
                          "p_elo": "" if p_elo is None else round(p_elo, 4),
                          "event_title": e.get("title", ""), "market_title": m.get("title", "")})
            mid = (bid + ask) / 2
            p_yes, proven, fam = weights.prob(series, tag, mid, p_elo)
            event = e.get("title", "")
            if e.get("sub_title"):
                event += f" ({e['sub_title']})"
            for side, price, prob in (("yes", ask, p_yes), ("no", round(1 - bid, 4), 1 - p_yes)):
                fee = config.FEE_RATE * price * (1 - price)
                cands.append({
                    "ticker": m["ticker"], "event_ticker": e.get("event_ticker", ""), "game": game_key(e.get("event_ticker", "")),
                    "side": side, "event": event, "series": series, "tag": tag,
                    "bet": f"{side.upper()} - {m.get('title') or m.get('yes_sub_title') or m['ticker']}",
                    "price": price, "prob": prob, "market_prob": mid if side == "yes" else 1 - mid,
                    "elo": None if p_elo is None else (p_elo if side == "yes" else 1 - p_elo),
                    "ev": prob - price - fee, "spread": ask - bid, "proven": proven, "family": fam,
                    "when": occ, "volume": liq})
    log(f"  scanned {n_events} sports events -> {n_markets} tradeable markets in window "
        f"({n_live} skipped as already live)")
    return snaps, cands


def _one_per_game(rows, n):
    out, seen = [], set()
    for r in rows:
        if r["game"] in seen:
            continue
        seen.add(r["game"])
        out.append(r)
        if len(out) >= n:
            break
    return out


def choose(cands):
    ok = [c for c in cands if c["spread"] <= config.MAX_SPREAD_PICK]
    likely = _one_per_game(sorted((c for c in ok if c["price"] <= config.LIKELY_MAX_PRICE),
                                  key=lambda c: (-c["prob"], -c["ev"])), config.N_LIKELY)
    value = _one_per_game(sorted((c for c in ok if c["proven"] and c["ev"] >= config.VALUE_MIN_EV),
                                 key=lambda c: -c["ev"]), config.N_VALUE)
    parlays = []
    for n in config.N_PARLAY_LEGS:
        legs = likely[:n]
        if len(legs) == n:
            p = price = 1.0
            for leg in legs:
                p *= leg["prob"]
                price *= leg["price"]
            parlays.append({"legs": legs, "prob": p, "price": price})
    return likely, value, parlays
