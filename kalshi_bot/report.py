"""Build the daily picks email (HTML + plain text) and send it."""
import html
import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo

from . import config

TZ = ZoneInfo(os.environ.get("PICKS_TZ", "America/Chicago"))


def pct(x):
    return "-" if x is None else f"{x * 100:.1f}%"


def cents(x):
    return f"{x * 100:.0f}c"


def record(picks, lst=None, days=None):
    now = datetime.now(timezone.utc).date()
    rows = [p for p in picks if p.get("result") in ("W", "L") and (lst is None or p["list"] == lst)
            and (days is None or (now - datetime.fromisoformat(p["date"]).date()).days <= days)]
    if not rows:
        return None
    w = sum(p["result"] == "W" for p in rows)
    pnl = sum(float(p["pnl"]) for p in rows)
    cost = sum(float(p["price"]) for p in rows)
    exp = sum(float(p["prob"]) for p in rows)
    return {"n": len(rows), "w": w, "l": len(rows) - w, "pnl": pnl, "roi": pnl / cost if cost else 0, "expected": exp}


def _record_line(name, r):
    if not r:
        return f"{name}: no graded picks yet"
    return (f"{name}: {r['w']}-{r['l']} ({r['w'] / r['n']:.0%}; model expected {r['expected']:.1f} wins) - "
            f"P/L ${r['pnl']:+.2f} per $1 contracts, ROI {r['roi']:+.1%}")


def build(likely, value, parlays, picks_log, weights, stats):
    now = datetime.now(TZ)
    subject = f"Kalshi Picks - {now:%b %-d} - {len(likely)} likely / {len(value)} value"
    proven = sorted(k for k, f in weights.get("families", {}).items() if f.get("proven"))

    def table(rows, cols):
        head = "".join(f"<th style='text-align:left;padding:4px 8px;border-bottom:1px solid #ccc'>{c}</th>" for c, _ in cols)
        body = ""
        for r in rows:
            body += "<tr>" + "".join(f"<td style='padding:4px 8px;border-bottom:1px solid #eee'>{html.escape(str(f(r)))}</td>"
                                     for _, f in cols) + "</tr>"
        return f"<table style='border-collapse:collapse;font-size:13px'><tr>{head}</tr>{body}</table>"

    cols = [("Sport", lambda r: r["tag"]), ("Event", lambda r: r["event"]), ("Bet", lambda r: r["bet"]),
            ("Buy at", lambda r: cents(r["price"])), ("Win chance", lambda r: pct(r["prob"])),
            ("Market says", lambda r: pct(r["market_prob"])), ("Ratings say", lambda r: pct(r["elo"])),
            ("Profit/$1 after fees", lambda r: f"{r['ev']:+.3f}")]

    rec_lines = [_record_line("Most likely list (all time)", record(picks_log, "likely")),
                 _record_line("Best value list (all time)", record(picks_log, "value")),
                 _record_line("Everything, last 14 days", record(picks_log, None, 14))]

    h = [f"<h2>Kalshi Picks - {now:%a %b %-d, %Y %-I:%M %p %Z}</h2>",
         f"<p>Scanned {stats['events']} open sports events / {stats['markets']} tradeable markets across "
         f"{stats['series']} market types. Only markets that start at least {config.PREGAME_BUFFER_HOURS}h from now "
         f"with tight bid/ask spreads are considered.</p>",
         "<h3>Track record (graded automatically from Kalshi results)</h3><ul>" +
         "".join(f"<li>{html.escape(x)}</li>" for x in rec_lines) + "</ul>",
         "<h3>Most likely to hit</h3>",
         f"<p>Only picks the bot itself rates at least {config.SAFE_MIN_PROB:.0%} likely (its own number, not Kalshi's price), "
         f"one per game, costing at most {cents(config.LIKELY_MAX_PRICE)}. "
         "A negative profit number means the price is higher than the fair value - it should hit often, "
         "but it loses money over time.</p>",
         table(likely, cols) if likely else "<p>Nothing qualified.</p>"]
    if parlays:
        h.append("<h3>Safest combos (built from the list above)</h3><ul>")
        for p in parlays:
            legs = " + ".join(f"{leg['bet']} [{leg['event']}] ({pct(leg['prob'])})" for leg in p["legs"])
            corr = ""
            if abs(p["prob"] - p.get("independent_prob", p["prob"])) > 0.002:
                corr = (f" (legs move together: {pct(p['independent_prob'])} if they were unrelated)"
                        if p["prob"] > p["independent_prob"] else f" (legs work against each other: {pct(p['independent_prob'])} if unrelated)")
            h.append(f"<li><b>{len(p['legs'])} legs: {pct(p['prob'])} to all hit</b>{html.escape(corr)} - {html.escape(legs)}</li>")
        h.append("</ul><p>Every leg must win, so the combined chance is lower than any single leg. Same-game legs are only "
                 "combined where the research shows they tend to hit together (e.g. one NBA player's points + rebounds); "
                 "combinations that work against each other (two teammates' overs, a player's over + his opponent winning) "
                 "are scored down.</p>")
    h.append("<h3>Best value</h3>")
    if value:
        h.append("<p>Where the model's win chance beats the price by the most after fees. Only market types where "
                 "the model has <i>proven</i> it beats the plain Kalshi price on held-out data are eligible.</p>")
        h.append(table(value, cols))
    else:
        h.append("<p>No value picks today. Either no market type has proven an edge over the plain Kalshi price yet, "
                 "or none of today's prices are far enough off. That is the honest answer, not a bug: the old bot's "
                 "biggest 'edges' (20%+) went 7-23.</p>")
    h.append("<h3>What the bot has learned</h3>")
    h.append(f"<p>Trained on {weights.get('n_rows', 0):,} settled markets (last update {weights.get('updated', 'never')}). "
             f"Market types where it beats Kalshi's price on held-out data: "
             f"{html.escape(', '.join(proven) if proven else 'none yet - it is trusting the market for now')}.</p>")
    h.append("<p style='color:#666;font-size:12px'>Statistical estimates, not guarantees. Never bet money you can't afford to lose.</p>")
    html_body = "\n".join(h)

    def line(r):
        return (f"  [{r['tag']}] {r['event']} | {r['bet']} | buy {cents(r['price'])} | win {pct(r['prob'])} "
                f"(market {pct(r['market_prob'])}) | profit/$1 {r['ev']:+.3f}")

    text = [f"Kalshi Picks - {now:%a %b %-d, %Y}", "", *rec_lines, "", "MOST LIKELY TO HIT:"]
    text += [line(r) for r in likely] or ["  nothing qualified"]
    for p in parlays:
        text.append(f"  {len(p['legs'])}-leg combo: {pct(p['prob'])} to all hit")
    text += ["", "BEST VALUE:"] + ([line(r) for r in value] or ["  none today (no proven edge yet)"])
    return subject, html_body, "\n".join(text)


def send(subject, html_body, text_body, log=print):
    user, pw = os.environ.get("GMAIL_ADDRESS"), os.environ.get("GMAIL_APP_PASSWORD")
    to = os.environ.get("PICKS_TO") or user
    if not (user and pw):
        log("  email not configured (GMAIL_ADDRESS / GMAIL_APP_PASSWORD) - skipping send")
        return False
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60) as s:
        s.login(user, pw)
        s.sendmail(user, [a.strip() for a in to.split(",")], msg.as_string())
    log(f"  emailed picks to {to}")
    return True
