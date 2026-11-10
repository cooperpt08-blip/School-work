"""Which factors make the favourite win MORE OFTEN THAN ITS PRICE SAYS?
(diff = actual wins minus price-expected wins; |z| >= 2 is the usual bar, and with ~40 groups
tested, 2 of them will cross it by pure chance.)"""
import csv, math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from kalshi_bot import store  # noqa: E402

def report(title, groups, min_n=10):
    print(f"\n== {title}")
    for k in sorted(groups, key=str):
        g = groups[k]
        if len(g) < min_n:
            continue
        n, w = len(g), sum(won for _, won in g)
        exp, var = sum(p for p, _ in g), sum(p * (1 - p) for p, _ in g)
        z = (w - exp) / math.sqrt(var)
        print(f"   {str(k):<44} n={n:<6} won {w / n:6.1%}  price said {exp / n:6.1%}  z={z:+.2f}{'  <--' if abs(z) >= 2 else ''}")

# ---- A) the 221 replayed games: bet = Kalshi favourite ------------------------------------
rows = [r for r in csv.DictReader(open(Path(__file__).parent / "old_picks_graded.csv")) if r["result"]]
A = defaultdict(lambda: defaultdict(list))
seen = set()
for r in rows:
    g = (r["matchup"], r["game_time"][:10])
    k, m = float(r["kalshi"]), float(r["model"])
    if g in seen or not 0.03 < k < 0.97:
        continue
    seen.add(g)
    fav_is_pick = k >= 0.5
    p = k if fav_is_pick else 1 - k
    won = (r["result"] == "W") == fav_is_pick
    model_p = m if fav_is_pick else 1 - m          # old model's view of the favourite
    away, home = r["matchup"].split(" at ")
    team = r["selection"].split(" wins by")[0]
    fav_home = (team == home) == fav_is_pick if r["type"] != "Total" else None
    gt, sent = datetime.fromisoformat(r["game_time"]), datetime.fromisoformat(r["sent"])
    A["Old model agrees the favourite is a favourite?"]["agrees" if model_p >= 0.5 else "DISAGREES"].append((p, won))
    A["Old model vs price on the favourite"]["model higher than price" if model_p > p else "model lower than price"].append((p, won))
    if fav_home is not None:
        A["Favourite is home or away"][f'{r["sport"]} fav {"home" if fav_home else "away"}'].append((p, won))
    A["Favourite price"]["50-60c" if p < .6 else "60-70c" if p < .7 else "70c+"].append((p, won))
    A["Hours between email and game"]["<12h" if (gt - sent).total_seconds() < 43200 else "12-36h" if (gt - sent).total_seconds() < 129600 else "36h+"].append((p, won))
for t, g in A.items():
    report("[221 replayed games] " + t, g)

# ---- B) 17k settled Kalshi markets ---------------------------------------------------------
res = store.load_results()
B = defaultdict(lambda: defaultdict(list))
def kind(series):
    for key in ("GAME", "MATCH"):
        if series.endswith(key):
            return "game winner"
    for key in ("SPREAD", "TOTAL", "1H", "2H", "1Q", "2Q", "3Q", "4Q", "1P", "2P", "3P", "WINMARGIN"):
        if key in series:
            return "spread/total/period"
    return "player/other prop"
for r in store.load_snapshots():
    y = res.get(r["ticker"])
    if y not in ("yes", "no"):
        continue
    bid, ask = float(r["yes_bid"]), float(r["yes_ask"])
    mid = (bid + ask) / 2
    p, won = (mid, y == "yes") if mid >= 0.5 else (1 - mid, y == "no")
    sp = ask - bid
    B["Bet type"][kind(r["series"])].append((p, won))
    B["Bid/ask spread at snapshot"]["1c" if sp <= .011 else "2-3c" if sp <= .031 else "4-6c"].append((p, won))
    d = datetime.fromisoformat(r["occurrence"])
    B["Day of week (event)"][d.strftime("%a")].append((p, won))
    B["Favourite is the YES or NO side"]["YES side" if mid >= 0.5 else "NO side"].append((p, won))
    if r["p_elo"]:
        e = float(r["p_elo"])
        e_fav = e if mid >= 0.5 else 1 - e
        B["Team ratings vs Kalshi on the favourite"][
            "ratings MORE bullish (+5pts)" if e_fav > p + .05 else "ratings LESS bullish (-5pts)" if e_fav < p - .05 else "ratings roughly agree"].append((p, won))
        B["Team ratings disagree on who's favoured?"]["ratings agree" if e_fav >= .5 else "ratings pick the OTHER team"].append((p, won))
for t, g in B.items():
    report("[17k Kalshi markets] " + t, g, min_n=40)
