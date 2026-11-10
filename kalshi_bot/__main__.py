"""Kalshi picks bot.

  python -m kalshi_bot daily          # what the scheduled GitHub Action runs every morning
  python -m kalshi_bot daily --no-email
  python -m kalshi_bot backfill --days 21
  python -m kalshi_bot learn
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

from . import config, model, ratings, report, scan, store
from .backfill import backfill


def log(msg):
    print(msg, flush=True)


def training_rows():
    results = store.load_results()
    latest = {}
    for r in store.load_snapshots():
        if results.get(r["ticker"]) not in ("yes", "no"):
            continue
        if r["ticker"] not in latest or r["snap_ts"] > latest[r["ticker"]]["snap_ts"]:
            latest[r["ticker"]] = r
    rows = []
    for r in latest.values():
        bid, ask = float(r["yes_bid"]), float(r["yes_ask"])
        p_elo = float(r["p_elo"]) if r["p_elo"] not in ("", None) else None
        rows.append({"t": r["snap_ts"], "x": model.features((bid + ask) / 2, p_elo),
                     "y": 1 if results[r["ticker"]] == "yes" else 0, "tag": r["tag"], "series": r["series"]})
    return rows


def run_learn():
    rows = training_rows()
    log(f"Learning from {len(rows)} settled markets")
    w = model.learn(rows, log=log)
    config.WEIGHTS.write_text(json.dumps(w, indent=1))
    return w


def weights_stale(days=6):
    if not config.WEIGHTS.exists():
        return True
    upd = json.loads(config.WEIGHTS.read_text()).get("updated")
    return not upd or (datetime.now(timezone.utc) - datetime.fromisoformat(upd)).days >= days


def run_daily(send_email=True, force_learn=False):
    log("1/5 Updating ESPN results for team ratings")
    ratings.update_games(log=log)
    log("2/5 Grading past picks / logged markets against Kalshi results")
    store.update_results(log=log)
    if force_learn or weights_stale():
        log("3/5 Re-learning weights")
        run_learn()
    else:
        log("3/5 Weights are fresh - skipping re-learn")
    log("4/5 Scanning every open Kalshi sports market")
    snaps, cands = scan.scan(log=log)
    store.append_snapshots(snaps)
    likely, value, parlays = scan.choose(cands)
    today = datetime.now(report.TZ).date().isoformat()
    picks = store.load_picks()
    already = {(p["date"], p["list"], p["ticker"], p["side"]) for p in picks}
    for lst, rows in (("likely", likely), ("value", value)):
        for r in rows:
            k = (today, lst, r["ticker"], r["side"])
            if k not in already:
                picks.append({"date": today, "list": lst, "ticker": r["ticker"], "event_ticker": r["event_ticker"],
                              "side": r["side"], "event": r["event"], "bet": r["bet"], "price": f"{r['price']:.4f}",
                              "prob": f"{r['prob']:.4f}", "ev": f"{r['ev']:.4f}", "family": r["family"]})
    store.save_picks(picks)
    log("5/5 Building report")
    weights = json.loads(config.WEIGHTS.read_text()) if config.WEIGHTS.exists() else {}
    stats = {"events": len({c["event_ticker"] for c in cands}), "markets": len(snaps),
             "series": len({c["series"] for c in cands})}
    subject, html_body, text_body = report.build(likely, value, parlays, picks, weights, stats)
    config.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (config.REPORT_DIR / "latest.html").write_text(html_body)
    (config.REPORT_DIR / "latest.txt").write_text(text_body)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fh:
            fh.write(html_body + "\n")
    log("\n" + text_body + "\n")
    if send_email:
        report.send(subject, html_body, text_body, log=log)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kalshi_bot")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("daily")
    d.add_argument("--no-email", action="store_true")
    d.add_argument("--learn", action="store_true", help="force a re-learn even if weights are fresh")
    b = sub.add_parser("backfill")
    b.add_argument("--days", type=int, default=21)
    b.add_argument("--per-series", type=int, default=400)
    b.add_argument("--series", default="", help="comma-separated series tickers (default: all active)")
    sub.add_parser("learn")
    sub.add_parser("update-games")
    a = ap.parse_args(argv)
    if a.cmd == "daily":
        run_daily(send_email=not a.no_email, force_learn=a.learn)
    elif a.cmd == "backfill":
        ratings.update_games(log=log)
        backfill(days=a.days, per_series=a.per_series, series=[s for s in a.series.split(",") if s] or None, log=log)
        run_learn()
    elif a.cmd == "learn":
        run_learn()
    elif a.cmd == "update-games":
        ratings.update_games(log=log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
