"""Everything the bot remembers: price snapshots, settlement results, and the picks it emailed."""
import csv
import gzip
import io
from datetime import datetime, timedelta, timezone

from . import config, kalshi

SNAP_FIELDS = ["snap_ts", "source", "ticker", "event_ticker", "series", "tag", "occurrence",
               "yes_bid", "yes_ask", "p_elo", "event_title", "market_title"]
PICK_FIELDS = ["date", "list", "ticker", "event_ticker", "side", "event", "bet", "price", "prob", "ev",
               "family", "result", "pnl"]


def append_snapshots(rows):
    config.SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    by_month = {}
    for r in rows:
        by_month.setdefault(r["snap_ts"][:7], []).append(r)
    for month, mrows in by_month.items():
        f = config.SNAPSHOTS / f"{month}.csv.gz"
        new = not f.exists()
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=SNAP_FIELDS)
        if new:
            w.writeheader()
        for r in mrows:
            w.writerow({k: r.get(k, "") for k in SNAP_FIELDS})
        with gzip.open(f, "at", newline="") as fh:  # appending a gzip member keeps the file valid
            fh.write(buf.getvalue())


def load_snapshots():
    rows = []
    if not config.SNAPSHOTS.exists():
        return rows
    for f in sorted(config.SNAPSHOTS.glob("*.csv.gz")):
        with gzip.open(f, "rt", newline="") as fh:
            rows.extend(csv.DictReader(fh))
    return rows


def load_results():
    if not config.RESULTS.exists():
        return {}
    with open(config.RESULTS, newline="") as fh:
        return {r["ticker"]: r["result"] for r in csv.DictReader(fh)}


def save_results(res):
    config.RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with open(config.RESULTS, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ticker", "result"])
        for t in sorted(res):
            w.writerow([t, res[t]])


def load_picks():
    if not config.PICKS_LOG.exists():
        return []
    with open(config.PICKS_LOG, newline="") as fh:
        return list(csv.DictReader(fh))


def save_picks(rows):
    config.PICKS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(config.PICKS_LOG, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=PICK_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in PICK_FIELDS})


def update_results(log=print):
    """Ask Kalshi how every logged market settled (only ones whose event should be over)."""
    res = load_results()
    now = datetime.now(timezone.utc)
    want = set()
    for r in load_snapshots():
        if r["ticker"] not in res and r["occurrence"] and kalshi.ts(r["occurrence"]) < now - timedelta(hours=2):
            want.add(r["ticker"])
    picks = load_picks()
    for p in picks:
        if p["ticker"] not in res:
            want.add(p["ticker"])
    log(f"  checking settlement for {len(want)} markets")
    for t, m in kalshi.markets_by_ticker(sorted(want)).items():
        if m.get("result") in ("yes", "no") or m.get("status") in ("settled", "finalized"):
            res[t] = m.get("result") or "void"
    save_results(res)
    # grade the emailed picks
    for p in picks:
        r = res.get(p["ticker"])
        if r in ("yes", "no") and not p.get("result"):
            won = (r == p["side"])
            price = float(p["price"])
            fee = config.FEE_RATE * price * (1 - price)
            p["result"] = "W" if won else "L"
            p["pnl"] = f"{(1 - price if won else -price) - fee:.4f}"
    save_picks(picks)
    return res
