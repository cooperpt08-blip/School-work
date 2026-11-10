"""Deeper look at the old bot's wins vs losses: every split is measured against what the Kalshi
price expected (wins - expected), with a z-score so small samples aren't over-read."""
import csv, math
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
rows = [r for r in csv.DictReader(open(HERE / "old_picks_graded.csv")) if r["result"]]
emails = [l.split("|") for l in (HERE / "old_picks_from_emails.psv").read_text().splitlines()]

# how many emails repeated each pick, and how its Kalshi price moved between first and last email
hist = defaultdict(list)
for sent, sport, typ, matchup, sel, gtime, model, kalshi, edge in emails:
    hist[(sport, typ, matchup, sel, gtime)].append((sent, float(kalshi) / 100))
for r in rows:
    k = (r["sport"], r["type"], r["matchup"], r["selection"],
         datetime.fromisoformat(r["game_time"]).strftime("%a %b %-d, %-I:%M %p"))
    h = sorted(hist.get(k, []))
    r["n_emails"] = len(h) or 1
    r["move"] = (h[-1][1] - h[0][1]) if len(h) > 1 else None
    for f in ("model", "kalshi", "edge"):
        r[f] = float(r[f])
    r["w"] = r["result"] == "W"
    gt, sent = datetime.fromisoformat(r["game_time"]), datetime.fromisoformat(r["sent"])
    r["lead_h"] = (gt - sent).total_seconds() / 3600
    away, home = r["matchup"].split(" at ")
    team = r["selection"].replace(" wins by", "|").split("|")[0].strip()
    r["side"] = "home" if team == home else "away" if team == away else "n/a"
    r["team"] = team
    r["dow"] = gt.strftime("%a")
    r["hour"] = gt.hour

def report(title, groups, min_n=8):
    print(f"\n== {title}")
    print(f"   {'group':<30}{'record':>9}  {'won':>5} {'price expected':>15} {'diff':>6}  {'z':>5}  P/L")
    for k in sorted(groups, key=str):
        g = groups[k]
        if len(g) < min_n:
            continue
        n, w = len(g), sum(r["w"] for r in g)
        exp = sum(r["kalshi"] for r in g)
        var = sum(r["kalshi"] * (1 - r["kalshi"]) for r in g)
        z = (w - exp) / math.sqrt(var) if var else 0
        pnl = sum((1 - r["kalshi"]) if r["w"] else -r["kalshi"] for r in g)
        flag = "  <-- notable" if abs(z) >= 2 else ""
        print(f"   {str(k):<30}{w:>4}-{n - w:<4}  {w:>5} {exp:>15.1f} {w - exp:>+6.1f}  {z:>+5.2f}  {pnl:+6.2f}{flag}")

def by(f, rs=rows):
    g = defaultdict(list)
    for r in rs:
        g[f(r)].append(r)
    return g

report("Sport + bet type", by(lambda r: f'{r["sport"]} {r["type"]}'))
ml = [r for r in rows if r["type"] == "Moneyline"]
report("Moneyline: home vs away pick", by(lambda r: f'{r["sport"]} {r["side"]}', ml))
report("Moneyline: favorite vs underdog (by Kalshi price)", by(lambda r: f'{r["sport"]} {"fav" if r["kalshi"] >= .5 else "dog"}', ml))
report("How far ahead the pick was made", by(lambda r: "a <12h" if r["lead_h"] < 12 else "b 12-36h" if r["lead_h"] < 36 else "c 36h+"))
report("Times the bot repeated the pick", by(lambda r: "1 email" if r["n_emails"] == 1 else "2 emails" if r["n_emails"] == 2 else "3+ emails"))
moved = [r for r in rows if r["move"] is not None]
report("Price moved between first and last email (closing-line value)",
       by(lambda r: "a market moved TOWARD pick (+2c+)" if r["move"] >= .02 else "c market moved AWAY (-2c+)" if r["move"] <= -.02 else "b flat", moved), min_n=5)
report("Day of week (game)", by(lambda r: r["dow"]))
report("Game start (local hour shown in email)", by(lambda r: "a before 6pm" if r["hour"] < 18 else "b 6-10pm" if r["hour"] < 22 else "c 10pm+"))
mlb_tot = [r for r in rows if r["sport"] == "MLB" and r["type"] == "Total"]
report("MLB totals by line", by(lambda r: r["selection"].split()[0] + " " + ("<=8.5" if float(r["selection"].split()[1]) <= 8.5 else "9.5-11.5" if float(r["selection"].split()[1]) <= 11.5 else "12.5+"), mlb_tot), min_n=4)
report("Edge size", by(lambda r: "a <8%" if r["edge"] < .08 else "b 8-12%" if r["edge"] < .12 else "c 12-20%" if r["edge"] < .2 else "d 20%+"))
report("Most-picked teams (5+ picks)", by(lambda r: r["team"], [r for r in rows if r["type"] == "Moneyline"]), min_n=5)

# the summer stretch: did it get worse over time?
report("By week picked", by(lambda r: datetime.fromisoformat(r["sent"]).strftime("wk of %b %d") if False else
                            ("Jul 10-16" if r["sent"] < "2026-07-17" else "Jul 17-23" if r["sent"] < "2026-07-24" else "Jul 24-30" if r["sent"] < "2026-07-31" else "Jul 31-Aug 4")))
