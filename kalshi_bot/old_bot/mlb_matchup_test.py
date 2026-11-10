"""Would MLB pitching matchups have beaten Kalshi's price in 2026?

For every 2026 regular-season game Kalshi listed, rebuild what was knowable BEFORE first pitch:
  * Kalshi's price ~3h before the game (archived candlesticks)
  * each probable starter's season-to-date ERA (what the old bot used) and FIP (skill-based)
  * Elo team ratings from prior results
Then train on the first 60% of the season and test on the last 40%.
"""
import json
import math
import re
import sys
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from kalshi_bot import kalshi, model  # noqa: E402
from kalshi_bot.ratings import Matcher  # noqa: E402

CACHE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/mlb_matchup_cache")
CACHE.mkdir(parents=True, exist_ok=True)
MLB = "https://statsapi.mlb.com/api/v1"


def cached(name, fn):
    f = CACHE / name
    if f.exists():
        return json.loads(f.read_text())
    v = fn()
    f.write_text(json.dumps(v))
    return v


def mlb(path):
    with urllib.request.urlopen(MLB + path, timeout=60) as r:
        return json.load(r)


# ---- 1. Kalshi markets + pre-game prices -------------------------------------------------
def kalshi_markets():
    ms = list(kalshi.paged("/historical/markets", "markets", {"series_ticker": "KXMLBGAME", "limit": 1000}))
    t0 = datetime(2026, 3, 1).timestamp()
    ms += list(kalshi.settled_markets("KXMLBGAME", t0, datetime(2026, 11, 1).timestamp()))
    return list({m["ticker"]: m for m in ms}.values())


markets = cached("markets.json", kalshi_markets)
by_event = defaultdict(list)
for m in markets:
    if m.get("result") in ("yes", "no"):
        by_event[m["event_ticker"]].append(m)


def pregame_quote(m):
    occ = kalshi.ts(m.get("occurrence_datetime") or m.get("expected_expiration_time"))
    at = occ.timestamp() - 6 * 3600
    # markets settled before Kalshi's archive cutoff (2026-09-11) only exist under /historical
    archived = (m.get("close_time") or "") < "2026-09-11"
    path = (f"/historical/markets/{m['ticker']}/candlesticks" if archived
            else f"/series/KXMLBGAME/markets/{m['ticker']}/candlesticks")
    for path in (path,):
        try:
            d = kalshi.get(path, {"start_ts": int(at - 12 * 3600), "end_ts": int(at), "period_interval": 60})
        except Exception:  # noqa: BLE001
            continue
        best = None
        for c in d.get("candlesticks") or []:
            bid, ask = c.get("yes_bid") or {}, c.get("yes_ask") or {}
            b = kalshi.dollars(bid.get("close_dollars", bid.get("close")))
            a = kalshi.dollars(ask.get("close_dollars", ask.get("close")))
            if b is not None and a is not None and 0 < b <= a < 1:
                best = (b, a)
        if best:
            return best
    return None


def all_quotes():
    out = {}
    kalshi.MIN_GAP = 0.45  # the archive endpoint rate-limits hard
    events = sorted(by_event)[::2]  # every other game: ~2,300 is plenty and halves the download
    for i, ev in enumerate(events):
        m = sorted(by_event[ev], key=lambda x: x["ticker"])[0]  # one side per game is enough
        q = pregame_quote(m)
        if q:
            out[m["ticker"]] = q
        if i % 500 == 0:
            print(f"  prices {i}/{len(events)}", flush=True)
    return out


quotes = cached("quotes.json", all_quotes)
print(f"{len(by_event)} Kalshi MLB games, {len(quotes)} with a pre-game price")

# ---- 2. MLB schedule with probable pitchers ----------------------------------------------
def schedule():
    games = []
    d = date(2026, 3, 20)
    while d < date(2026, 10, 5):
        e = min(d + timedelta(days=30), date(2026, 10, 5))
        j = mlb(f"/schedule?sportId=1&gameType=R&startDate={d}&endDate={e}&hydrate=probablePitcher")
        for day in j.get("dates", []):
            for g in day["games"]:
                if g.get("status", {}).get("abstractGameState") != "Final":
                    continue
                t = g["teams"]
                games.append({"date": day["date"], "pk": g["gamePk"], "dh": g.get("doubleHeader", "N"),
                              "home": t["home"]["team"]["name"], "away": t["away"]["team"]["name"],
                              "hp": (t["home"].get("probablePitcher") or {}).get("id"),
                              "ap": (t["away"].get("probablePitcher") or {}).get("id")})
        d = e + timedelta(days=1)
    return games


sched = cached("schedule.json", schedule)
pitchers = sorted({p for g in sched for p in (g["hp"], g["ap"]) if p})
print(f"{len(sched)} MLB games, {len(pitchers)} probable starters")


def gamelogs():
    def one(pid):
        try:
            j = mlb(f"/people/{pid}/stats?stats=gameLog&group=pitching&season=2026")
            return str(pid), [{"date": s["date"], **{k: s["stat"].get(k, 0) for k in
                               ("outs", "earnedRuns", "strikeOuts", "baseOnBalls", "hitByPitch", "homeRuns")}}
                              for s in (j.get("stats") or [{}])[0].get("splits", [])]
        except Exception:  # noqa: BLE001
            return str(pid), []
    with ThreadPoolExecutor(8) as pool:
        return dict(pool.map(one, pitchers))


logs = cached("gamelogs.json", gamelogs)
LG_ERA, FIP_C = 4.1, 3.1


def asof(pid, day):
    """Season-to-date ERA and FIP using only games BEFORE `day` (regressed toward league average)."""
    outs = er = k = bb = hr = 0
    for s in logs.get(str(pid), []):
        if s["date"] < day:
            outs += s["outs"]; er += s["earnedRuns"]; k += s["strikeOuts"]
            bb += s["baseOnBalls"] + s["hitByPitch"]; hr += s["homeRuns"]
    ip = outs / 3
    era = er * 9 / ip if ip else LG_ERA
    fip = (13 * hr + 3 * bb - 2 * k) / ip + FIP_C if ip else LG_ERA
    w = ip / (ip + 40)  # ~40 IP of league-average prior: early-season ERAs are mostly noise
    return w * era + (1 - w) * LG_ERA, w * fip + (1 - w) * LG_ERA, ip


# ---- 3. join everything ------------------------------------------------------------------
sched_by = defaultdict(list)
for g in sched:
    sched_by[g["date"]].append(g)
matcher = Matcher()
rows = []
for ev, ms in by_event.items():
    m = sorted(ms, key=lambda x: x["ticker"])[0]
    q = quotes.get(m["ticker"])
    if not q:
        continue
    title = (m.get("rules_primary") or "")
    mm = re.search(r"the (.+? vs\.? .+?) (?:Pro|professional|game|Baseball)", title)
    p_elo, eg = matcher.game_prob("KXMLBGAME", ev, mm.group(1) if mm else "", m.get("yes_sub_title"))
    if eg is None:
        continue
    cands = [g for g in sched_by.get(eg["date"], []) if g["home"] == eg["home"] and g["away"] == eg["away"]]
    if len(cands) != 1 or not cands[0]["hp"] or not cands[0]["ap"]:
        continue  # skip doubleheaders / missing probables
    g = cands[0]
    yes_home = abs(p_elo - matcher.elo["KXMLBGAME"].pregame[eg["event_id"]]) < 1e-9
    he, hf, hip = asof(g["hp"], g["date"])
    ae, af, aip = asof(g["ap"], g["date"])
    # positive = YES team's starter is better (lower ERA/FIP)
    sgn = 1 if yes_home else -1
    rows.append({"date": g["date"], "mid": (q[0] + q[1]) / 2, "ask": q[1], "bid": q[0], "elo": p_elo,
                 "era_edge": sgn * (ae - he), "fip_edge": sgn * (af - hf), "y": 1 if m["result"] == "yes" else 0})
rows.sort(key=lambda r: r["date"])
print(f"{len(rows)} games joined (price + both probable starters + ratings)\n")

# ---- 4. walk-forward test ----------------------------------------------------------------
def X(r, use):
    x = [1.0, model.logit(r["mid"])]
    if "elo" in use:
        x.append(model.logit(r["elo"]) - model.logit(r["mid"]))
    if "era" in use:
        x.append(r["era_edge"] / 2)
    if "fip" in use:
        x.append(r["fip_edge"] / 2)
    return x


def fit(data, k, lam=2.0):
    th = [0.0, 1.0] + [0.0] * (k - 2)
    prior = th[:]
    for _ in range(50):
        g = [lam * (th[i] - prior[i]) for i in range(k)]
        H = [[lam if i == j else 0.0 for j in range(k)] for i in range(k)]
        for x, y in data:
            p = model.sigmoid(sum(a * b for a, b in zip(th, x)))
            for i in range(k):
                g[i] += (p - y) * x[i]
                for j in range(k):
                    H[i][j] += p * (1 - p) * x[i] * x[j]
        # solve H d = g (small k, Gaussian elimination)
        M = [H[i][:] + [g[i]] for i in range(k)]
        for c in range(k):
            piv = max(range(c, k), key=lambda r_: abs(M[r_][c]))
            M[c], M[piv] = M[piv], M[c]
            for r_ in range(k):
                if r_ != c:
                    f = M[r_][c] / M[c][c]
                    for j in range(c, k + 1):
                        M[r_][j] -= f * M[c][j]
        d = [M[i][k] / M[i][i] for i in range(k)]
        th = [th[i] - d[i] for i in range(k)]
        if max(abs(v) for v in d) < 1e-8:
            break
    return th


cut = int(len(rows) * 0.6)
train, test = rows[:cut], rows[cut:]
print(f"train {train[0]['date']}..{train[-1]['date']} ({len(train)})   test {test[0]['date']}..{test[-1]['date']} ({len(test)})")
base = [-(r["y"] * math.log(r["mid"]) + (1 - r["y"]) * math.log(1 - r["mid"])) for r in test]
print(f"\n{'model':<36}{'test log-loss':>14}{'gain vs Kalshi':>16}{'z':>7}   weights")
print(f"{'Kalshi price alone':<36}{sum(base) / len(base):>14.4f}")
results = {}
for name, use in (("+ team ratings (Elo)", ("elo",)), ("+ starter ERA (old bot's input)", ("era",)),
                  ("+ starter FIP (skill-based)", ("fip",)), ("+ Elo + ERA + FIP", ("elo", "era", "fip"))):
    data = [(X(r, use), r["y"]) for r in train]
    th = fit(data, len(data[0][0]))
    probs = [model.sigmoid(sum(a * b for a, b in zip(th, X(r, use)))) for r in test]
    ll = [-(r["y"] * math.log(p) + (1 - r["y"]) * math.log(1 - p)) for r, p in zip(test, probs)]
    d = [b - a for a, b in zip(ll, base)]
    mean = sum(d) / len(d)
    sd = math.sqrt(sum((v - mean) ** 2 for v in d) / (len(d) - 1))
    results[name] = probs
    print(f"{name:<36}{sum(ll) / len(ll):>14.4f}{mean:>+16.4f}{mean / (sd / math.sqrt(len(d))):>+7.2f}   {[round(v, 3) for v in th]}")

# ---- 5. what it would have meant for picks --------------------------------------------------
print("\nBetting the test-period games (buy at the ask, Kalshi fee included):")


def sim(label, probs, min_edge):
    n = w = 0
    pnl = 0.0
    for r, p in zip(test, probs):
        yes_ev = p - r["ask"] - 0.07 * r["ask"] * (1 - r["ask"])
        no_price = 1 - r["bid"]
        no_ev = (1 - p) - no_price - 0.07 * no_price * (1 - no_price)
        if max(yes_ev, no_ev) < min_edge:
            continue
        side_yes = yes_ev >= no_ev
        price = r["ask"] if side_yes else no_price
        won = (r["y"] == 1) == side_yes
        n += 1
        w += won
        pnl += (1 - price if won else -price) - 0.07 * price * (1 - price)
    if n:
        print(f"   {label:<46} {w:>4}-{n - w:<4} {w / n:6.1%}   P/L ${pnl:+7.2f}  ROI {pnl / n:+.1%} per bet")
    else:
        print(f"   {label:<46} no bets")


fav = [r["mid"] for r in test]
n = len(test)
w = sum((r["y"] == 1) == (r["mid"] >= 0.5) for r in test)
print(f"   {'Always take the Kalshi favourite':<46} {w:>4}-{n - w:<4} {w / n:6.1%}")
for name, probs in results.items():
    sim(f"{name}, edge >= 2c", probs, 0.02)
