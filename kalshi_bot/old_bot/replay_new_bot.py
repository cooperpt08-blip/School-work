"""Replay the new bot's 'most likely to hit' rule on the games the old bot picked.

For each old pick we know Kalshi's price for the side the old bot chose and how that side did.
The new bot (no proven edge in MLB/WNBA/MLS/FIFA) takes whichever side Kalshi favoured: if the
old pick was the underdog, the new bot's bet is the NO side of the same contract, which wins
exactly when the old pick lost."""
import csv
from collections import defaultdict
from pathlib import Path

FEE = 0.07
rows = [r for r in csv.DictReader(open(Path(__file__).parent / "old_picks_graded.csv")) if r["result"]]

def game(r):  # one bet per game (the old bot sometimes listed a game on several days)
    return (r["matchup"], r["game_time"][:10])

def simulate(min_prob=0.5, max_price=0.92):
    best = {}
    for r in rows:
        k = float(r["kalshi"])
        if k <= 0.03 or k >= 0.97:      # new bot skips decided/live markets (the 1c Lynx game)
            continue
        side_p, won = (k, r["result"] == "W") if k >= 0.5 else (1 - k, r["result"] == "L")
        if side_p > max_price or side_p < min_prob:
            continue
        g = game(r)
        if g not in best or side_p > best[g][0]:
            best[g] = (side_p, won, r["sport"], r["type"])
    return list(best.values())

def show(title, bets):
    n, w = len(bets), sum(b[1] for b in bets)
    exp = sum(b[0] for b in bets)
    pnl = sum(((1 - p) if won else -p) - FEE * p * (1 - p) for p, won, *_ in bets)
    cost = sum(b[0] for b in bets)
    print(f"{title:<44}{w:>4}-{n - w:<4}{w / n:>7.1%}   expected {exp / n:.1%}   P/L after fees ${pnl:+.2f}  ROI {pnl / cost:+.1%}")

old = {}
for r in rows:
    old.setdefault(game(r), r)
o = list(old.values())
ow = sum(r["result"] == "W" for r in o)
print(f"{'OLD bot, same games (first pick per game)':<44}{ow:>4}-{len(o) - ow:<4}{ow / len(o):>7.1%}")
show("NEW bot rule: Kalshi favourite, <=92c", simulate())
show("  ...only favourites priced 65c+", simulate(min_prob=0.65))
show("  ...only favourites priced 80c+", simulate(min_prob=0.80))
by = defaultdict(list)
for b in simulate():
    by[f"  {b[2]} {b[3]}"].append(b)
for k in sorted(by):
    if len(by[k]) >= 5:
        show(k, by[k])
