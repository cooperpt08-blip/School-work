"""Player props: does anything about the player, his matchup, or the conditions predict whether he
clears the line - beyond Kalshi's own price? And how do same-game legs move together (parlays)?

For each Kalshi prop market (e.g. "Trey Murphy III: 25+ points") everything is rebuilt from games
BEFORE that night:
  player form     season (decayed) average, last-5 average, game-to-game spread, minutes & role trend
  matchup         what this opponent allows to his position (vs league average), both teams' pace
  conditions      his personal home/away split, back-to-back, NFL wind/cold
  roster news     teammates missing tonight (more shots/targets), his own recent absences
  game script     sportsbook total and spread (big favourite -> blowout -> starters sit)
"""
import gzip
import json
import math
import re
import unicodedata
from collections import defaultdict, deque
from datetime import timedelta

from . import analysis as A
from . import features as F
from . import places

STATS = {  # series -> (league, how to read the stat from an ESPN player line, position groups)
    "KXNBAPTS": ("nba", lambda s: F.num(s.get("points"))),
    "KXNBAREB": ("nba", lambda s: F.num(s.get("rebounds"))),
    "KXNBAAST": ("nba", lambda s: F.num(s.get("assists"))),
    "KXNBA3PT": ("nba", lambda s: F.num(str(s.get("threePointFieldGoalsMade-threePointFieldGoalsAttempted", "0-0")).split("-")[0])),
    "KXNFLRECYDS": ("nfl", lambda s: F.num(s.get("receivingYards"), None)),
    "KXNFLRSHYDS": ("nfl", lambda s: F.num(s.get("rushingYards"), None)),
    "KXNFLPASSYDS": ("nfl", lambda s: F.num(s.get("passingYards"), None)),
}


def norm_name(n):
    n = unicodedata.normalize("NFKD", n or "").encode("ascii", "ignore").decode().lower()
    n = re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", "", n)
    return re.sub(r"[^a-z]", "", n)


def pos_group(league, pos):
    pos = (pos or "").upper()
    if league == "nba":
        return "C" if pos == "C" else "G" if "G" in pos else "F"
    return pos if pos in ("WR", "TE", "RB", "QB") else "OTHER"


def player_lines(league, g, series):
    """{player_id: dict} for this game (merging NFL stat groups)."""
    read = STATS[series][1]
    out = {}
    for p in g["players"]:
        if not p.get("id"):
            continue
        d = out.setdefault(p["id"], {"name": p["name"], "pos": p.get("pos"), "side": p["side"], "dnp": p.get("dnp"),
                                     "minutes": 0.0, "stat": None})
        if p.get("pos"):
            d["pos"] = p["pos"]
        v = read(p.get("stats") or {})
        if v is not None:
            d["stat"] = (d["stat"] or 0) + v
        if league == "nba":
            d["minutes"] = F.num((p.get("stats") or {}).get("minutes"))
    for d in out.values():
        if d["stat"] is None:
            d["stat"] = 0.0
    return out


def build(series, log=print):
    league = STATS[series][0]
    games = F.load_games(league)
    f = F.DATA / f"kalshi_{series}.jsonl.gz"
    if not f.exists():
        return []
    markets = defaultdict(list)  # (date code, name) -> markets
    with gzip.open(f, "rt") as fh:
        for line in fh:
            m = json.loads(line)
            name = (m.get("title") or "").split(":")[0]
            markets[(m["event_ticker"].split("-")[1][:7], norm_name(name))].append(m)
    mon = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()
    team_rows = {r["id"]: r for r in F.build(league)} if league == "nfl" else {r["id"]: r for r in F.build(league)}
    hist = defaultdict(list)                        # player -> [(t, stat, minutes, home)]
    allowed = defaultdict(lambda: defaultdict(list))  # defense team -> position -> [stat allowed per game]
    league_pos = defaultdict(lambda: deque(maxlen=400))
    pace = defaultdict(list)
    rows = []
    for g in games:
        if g.get("season_type") == 1:
            continue
        t = g["t"]
        lines = player_lines(league, g, series)
        tr = team_rows.get(g["id"], {})
        local = t - timedelta(hours=5)
        codes = [f"{d:%y}{mon[d.month - 1]}{d:%d}" for d in (local, local - timedelta(days=1), local + timedelta(days=1))]
        for pid, d in lines.items():
            ms = next((markets[(c, norm_name(d["name"]))] for c in codes if markets.get((c, norm_name(d["name"])))), None)
            if not ms:
                continue
            side = d["side"]
            team = g["teams"][side]["abbr"]
            opp = g["teams"]["away" if side == "home" else "home"]["abbr"]
            hs = hist[pid]
            if len(hs) < 5:
                continue
            vals = [x[1] for x in hs]
            w = [0.5 ** (i / 8) for i in range(len(vals))][::-1]
            mean = sum(a * b for a, b in zip(vals, w)) / sum(w)
            sd = math.sqrt(sum(b * (a - mean) ** 2 for a, b in zip(vals, w)) / sum(w)) or 1.0
            last5 = sum(vals[-5:]) / 5
            home_vals = [x[1] for x in hs if x[3]] or vals
            away_vals = [x[1] for x in hs if not x[3]] or vals
            split = (sum(home_vals) / len(home_vals) - sum(away_vals) / len(away_vals)) * (1 if side == "home" else -1)
            pg = pos_group(league, d["pos"])
            opp_allowed = allowed[opp][pg][-15:]
            lg = list(league_pos[pg])
            opp_ratio = ((sum(opp_allowed) / len(opp_allowed)) / (sum(lg) / len(lg))) if opp_allowed and lg and sum(lg) else 1.0
            mins = [x[2] for x in hs]
            pre = "h_" if side == "home" else "a_"
            sb_total = next((ln.get("total") for ln in g.get("lines") or [] if ln.get("total")), None)
            sb_spread = next((ln.get("spread") for ln in g.get("lines") or [] if ln.get("spread") is not None), None)
            team_spread = (sb_spread if side == "home" else -sb_spread) if sb_spread is not None else None
            opp_pace = sum(pace[opp][-10:]) / len(pace[opp][-10:]) if pace[opp] else None
            for m in ms:
                strike = F.num(m.get("floor_strike"), None)
                if strike is None or m.get("result") not in ("yes", "no"):
                    continue
                q3 = F.snapshot(m["candles"], t.timestamp() - 3 * 3600)
                if not q3:
                    continue
                p3 = (q3[0] + q3[1]) / 2
                proj = mean * (opp_ratio ** 0.5)
                model_p = 0.5 * math.erfc((strike + 0.5 - proj) / (max(sd, 1.0) * math.sqrt(2)))
                x = {
                    "proj_vs_price": A.logit(min(max(model_p, .02), .98)) - A.logit(p3),
                    "cushion_season": (mean - strike) / max(sd, 1.0),
                    "hot_hand_last5_vs_season": (last5 - mean) / max(sd, 1.0),
                    "consistency_low_sd": -sd / max(mean, 1.0),
                    "opp_allows_position": opp_ratio,
                    "home_away_split": split / max(sd, 1.0),
                    "back_to_back": tr.get(pre + "b2b", 0),
                    "rest_days": tr.get(pre + "rest", 2),
                    "teammates_missing_share": tr.get(pre + "missing_share", 0),
                    "own_team_favored_by": -(team_spread or 0),
                    "blowout_risk": abs(team_spread or 0),
                    "game_total_line": sb_total or 0,
                    "role_trend_minutes": (sum(mins[-3:]) / 3 - sum(mins) / len(mins)) if league == "nba" else 0,
                    "travel_km": tr.get(pre + "travel_km", 0),
                }
                if league == "nba" and opp_pace:
                    x["opp_pace"] = opp_pace
                if league == "nfl" and "temp_f" in tr:
                    x["wind_mph"] = tr["wind_mph"]
                    x["cold"] = 1 if tr["temp_f"] < 40 else 0
                rows.append({"x": x, "y": 1 if m["result"] == "yes" else 0, "p": p3, "date": g["date"],
                             "game": g["id"], "player": d["name"], "team": team, "side": side, "series": series,
                             "strike": strike, "model_p": model_p})
        # ---- update history with tonight's results (after rows are built)
        per_def = defaultdict(lambda: defaultdict(float))
        for pid, d in lines.items():
            if d.get("dnp"):
                continue
            if league == "nba" and d["minutes"] <= 0:
                continue
            hist[pid].append((t, d["stat"], d["minutes"], d["side"] == "home"))
            if len(hist[pid]) > 60:
                hist[pid] = hist[pid][-60:]
            opp = g["teams"]["away" if d["side"] == "home" else "home"]["abbr"]
            per_def[opp][pos_group(league, d["pos"])] += d["stat"]
        for dteam, byp in per_def.items():
            for pg, v in byp.items():
                allowed[dteam][pg].append(v)
                league_pos[pg].append(v)
        if league == "nba":
            for side in ("home", "away"):
                st = g["teams"][side].get("stats") or {}
                p_ = F.num(st.get("fieldGoalsMade-fieldGoalsAttempted_b")) - F.num(st.get("offensiveRebounds")) + F.num(st.get("totalTurnovers")) + 0.44 * F.num(st.get("freeThrowsMade-freeThrowsAttempted_b"))
                pace[g["teams"][side]["abbr"]].append(p_)
    log(f"  {series}: {len(rows)} priced prop markets matched to players")
    return rows


def correlations(prop_rows, league, log=print):
    """Same-game legs: how often do two legs hit together vs. what the prices imply if independent?"""
    games = {}
    px = F.kalshi_game_prices(league)
    trows = {r["id"]: r for r in F.attach_market(F.build(league), league) if "kalshi_home_3h" in r}
    for r in prop_rows:
        games.setdefault(r["game"], []).append(r)
    pairs = defaultdict(list)
    for gid, legs in games.items():
        tr = trows.get(gid)
        for i, a in enumerate(legs):
            if tr:
                win = tr["home_win"] if a["side"] == "home" else 1 - tr["home_win"]
                pw = tr["kalshi_home_3h"] if a["side"] == "home" else 1 - tr["kalshi_home_3h"]
                pairs["player over + HIS team wins"].append((a["y"], win, a["p"], pw))
                pairs["player over + OTHER team wins"].append((a["y"], 1 - win, a["p"], 1 - pw))
            for b in legs[i + 1:]:
                if a["player"] == b["player"]:
                    if a["series"] != b["series"]:
                        pairs["same player, two different stats"].append((a["y"], b["y"], a["p"], b["p"]))
                    continue
                key = "two teammates both over" if a["side"] == b["side"] else "two opponents both over"
                if a["series"] == b["series"]:
                    pairs[key + " (same stat)"].append((a["y"], b["y"], a["p"], b["p"]))
    out = {}
    for k, v in pairs.items():
        if len(v) < 80:
            continue
        n = len(v)
        both = sum(a * b for a, b, _, _ in v) / n
        implied = sum(pa * pb for _, _, pa, pb in v) / n
        ya, yb = sum(a for a, *_ in v) / n, sum(b for _, b, *_ in v) / n
        indep = ya * yb
        se = math.sqrt(both * (1 - both) / n) or 1e-9
        out[k] = {"n": n, "both_hit": both, "if_independent": indep, "prices_imply": implied,
                  "lift_vs_independent": both / indep if indep else None, "z_vs_prices": (both - implied) / se}
    return out
