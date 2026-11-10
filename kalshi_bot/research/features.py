"""Turn the raw ESPN + Kalshi data into one row per game of PRE-GAME factors (nothing from the game
itself leaks in: every team/player/referee number comes from earlier games only).

Groups of factors (home-minus-away unless noted):
  performance  - offensive / defensive efficiency, shooting, turnovers, rebounding, yards per play ...
  style        - pace, shot profile (rim / mid-range / three / pull-ups / drives), run-pass mix, 4th-down aggression
  matchup      - a team's strength against the opponent's matching weakness
  form         - last-5 results and margins, streaks, Elo, results vs. Kalshi's own price (market over/underrating)
  roster       - regulars missing (minutes / yards share), QB change, players returning
  schedule     - rest, back-to-backs, games in last 4/7 days, road-trip length, travel km, time zones, altitude,
                 short week / bye, early body-clock kickoffs
  environment  - dome, temperature, wind, rain/snow (NFL, from Open-Meteo)
  officials    - the crew's past home-win and scoring tendencies
  context      - national TV / primetime, day of week, conference game, season phase, playoffs, neutral/international
  market       - Kalshi open price, line movement, volume, spread; sportsbook (DraftKings) line vs Kalshi
"""
import gzip
import json
import math
import time
import urllib.request
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import places

DATA = Path(__file__).resolve().parent / "data"
INTL = {"London": (51.556, -0.280), "Munich": (48.219, 11.625), "Frankfurt": (50.069, 8.645), "Mexico City": (19.303, -99.150),
        "Sao Paulo": (-23.545, -46.474), "São Paulo": (-23.545, -46.474), "Madrid": (40.453, -3.688), "Dublin": (53.335, -6.228),
        "Berlin": (52.507, 13.444), "Paris": (48.839, 2.253), "Melbourne": (-37.82, 144.98), "Abu Dhabi": (24.47, 54.60)}
NATIONAL_TV = {"ESPN", "ABC", "TNT", "NBA TV", "NBC", "Peacock", "Prime Video", "Amazon", "FOX", "CBS", "NFL Network", "ESPN2"}


def num(x, d=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def parse_ts(s):
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    if len(s) == 22 and s[16] == "+":  # '2026-01-15T03:00+00:00'
        s = s[:16] + ":00" + s[16:]
    return datetime.fromisoformat(s).astimezone(timezone.utc)


def load_games(league):
    with gzip.open(DATA / f"{league}_games.jsonl.gz", "rt") as fh:
        games = [json.loads(line) for line in fh]
    games = [g for g in games if g.get("start") and all(g["teams"][s].get("score") is not None for s in ("home", "away"))]
    for g in games:
        g["t"] = parse_ts(g["start"])
    return sorted(games, key=lambda g: g["t"])


# ------------------------------------------------------------------------------------------
# per team-game box-score numbers
def nba_box(me, opp):
    s, o = me.get("stats", {}), opp.get("stats", {})
    sh, osh = me.get("shots", {}), opp.get("shots", {})

    def poss(x):
        return (num(x.get("fieldGoalsMade-fieldGoalsAttempted_b")) - num(x.get("offensiveRebounds"))
                + num(x.get("totalTurnovers", x.get("turnovers"))) + 0.44 * num(x.get("freeThrowsMade-freeThrowsAttempted_b")))
    p = max(1.0, (poss(s) + poss(o)) / 2)
    fga = max(1.0, num(s.get("fieldGoalsMade-fieldGoalsAttempted_b")))
    ofga = max(1.0, num(o.get("fieldGoalsMade-fieldGoalsAttempted_b")))
    tpa, otpa = num(s.get("threePointFieldGoalsMade-threePointFieldGoalsAttempted_b")), num(o.get("threePointFieldGoalsMade-threePointFieldGoalsAttempted_b"))
    shots = max(1.0, sum(sh.get(k, 0) for k in ("rim_att", "midrange_att", "three_att", "other_att")))
    oshots = max(1.0, sum(osh.get(k, 0) for k in ("rim_att", "midrange_att", "three_att", "other_att")))
    return {
        "pts": me["score"], "opp_pts": opp["score"], "pace": p,
        "off_rtg": 100 * me["score"] / p, "def_rtg": 100 * opp["score"] / p,
        "three_rate": tpa / fga, "three_pct": num(s.get("threePointFieldGoalsMade-threePointFieldGoalsAttempted_a")) / max(1, tpa),
        "opp_three_rate": otpa / ofga, "opp_three_pct": num(o.get("threePointFieldGoalsMade-threePointFieldGoalsAttempted_a")) / max(1, otpa),
        "ft_rate": num(s.get("freeThrowsMade-freeThrowsAttempted_b")) / fga, "opp_ft_rate": num(o.get("freeThrowsMade-freeThrowsAttempted_b")) / ofga,
        "oreb_pct": num(s.get("offensiveRebounds")) / max(1, num(s.get("offensiveRebounds")) + num(o.get("defensiveRebounds"))),
        "tov_pct": num(s.get("totalTurnovers", s.get("turnovers"))) / p, "forced_tov_pct": num(o.get("totalTurnovers", o.get("turnovers"))) / p,
        "ast_rate": num(s.get("assists")) / max(1, num(s.get("fieldGoalsMade-fieldGoalsAttempted_a"))),
        "rim_share": sh.get("rim_att", 0) / shots, "mid_share": sh.get("midrange_att", 0) / shots,
        "rim_fg": sh.get("rim_made", 0) / max(1, sh.get("rim_att", 0)),
        "opp_rim_share": osh.get("rim_att", 0) / oshots, "opp_rim_fg": osh.get("rim_made", 0) / max(1, osh.get("rim_att", 0)),
        "pullup_share": sh.get("pullup_att", 0) / shots, "drive_share": sh.get("drive_att", 0) / shots,
        "fastbreak_pts": num(s.get("fastBreakPoints")), "paint_pts": num(s.get("pointsInPaint")),
        "opp_paint_pts": num(o.get("pointsInPaint")), "blocks": num(s.get("blocks")), "steals": num(s.get("steals")),
    }


def nfl_box(me, opp):
    s, o = me.get("stats", {}), opp.get("stats", {})
    plays, oplays = max(1.0, num(s.get("totalOffensivePlays"))), max(1.0, num(o.get("totalOffensivePlays")))
    patt, opatt = num(s.get("completionAttempts_b")), num(o.get("completionAttempts_b"))
    ratt, oratt = num(s.get("rushingAttempts")), num(o.get("rushingAttempts"))
    return {
        "pts": me["score"], "opp_pts": opp["score"], "plays": plays,
        "ypp": num(s.get("totalYards")) / plays, "def_ypp": num(o.get("totalYards")) / oplays,
        "pass_ypa": num(s.get("netPassingYards")) / max(1, patt), "def_pass_ypa": num(o.get("netPassingYards")) / max(1, opatt),
        "rush_ypc": num(s.get("rushingYards")) / max(1, ratt), "def_rush_ypc": num(o.get("rushingYards")) / max(1, oratt),
        "run_rate": ratt / max(1, ratt + patt), "opp_run_rate": oratt / max(1, oratt + opatt),
        "third_pct": num(s.get("thirdDownEff_a")) / max(1, num(s.get("thirdDownEff_b"))),
        "def_third_pct": num(o.get("thirdDownEff_a")) / max(1, num(o.get("thirdDownEff_b"))),
        "fourth_att": num(s.get("fourthDownEff_b")),
        "rz_pct": num(s.get("redZoneAttempts_a")) / max(1, num(s.get("redZoneAttempts_b"))),
        "def_rz_pct": num(o.get("redZoneAttempts_a")) / max(1, num(o.get("redZoneAttempts_b"))),
        "giveaways": num(s.get("turnovers")), "takeaways": num(o.get("turnovers")),
        "sacks_taken": num(s.get("sacksYardsLost_a")), "sacks_made": num(o.get("sacksYardsLost_a")),
        "pen_yds": num(s.get("totalPenaltiesYards_b")), "top": num(s.get("possessionTime"), 30),
        "pts_per_drive": me["score"] / max(1, num(s.get("totalDrives"), 11)),
        "def_pts_per_drive": opp["score"] / max(1, num(o.get("totalDrives"), 11)),
    }


# ------------------------------------------------------------------------------------------
def elo_prob(d):
    return 1 / (1 + 10 ** (-d / 400))


def decayed_mean(hist, key, half_life):
    if not hist:
        return None
    w = s = 0.0
    for i, h in enumerate(reversed(hist)):
        if key in h:
            wi = 0.5 ** (i / half_life)
            w += wi
            s += wi * h[key]
    return s / w if w else None


# ------------------------------------------------------------------------------------------
_WX = {}
_WX_FAILED = set()  # stadiums whose download failed this run (daily cap) - do not retry per game


def weather(lat, lon, t):
    """Hourly weather at kickoff from Open-Meteo. One request per stadium covers the whole history
    (the free tier has a DAILY request cap, so never request game by game). Cached on disk."""
    loc = f"{lat:.2f},{lon:.2f}"
    f = DATA / "weather_hourly.json"
    if not _WX and f.exists():
        _WX.update(json.loads(f.read_text()))
    hour = f"{t:%Y-%m-%dT%H}:00"
    series = _WX.get(loc)
    if series is None or (hour not in series["i"] and hour <= series["fetched_to"]):
        if series is not None and hour <= series["fetched_to"]:
            return None
        end = (datetime.now(timezone.utc) - timedelta(days=6)).date()
        if t.date() > end or loc in _WX_FAILED:
            return None  # too recent for the archive; the live bot uses the forecast API instead
        url = (f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}"
               f"&start_date=2024-08-01&end_date={end}&hourly=temperature_2m,wind_speed_10m,wind_gusts_10m,"
               f"precipitation,snowfall&timezone=UTC&temperature_unit=fahrenheit&wind_speed_unit=mph")
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                h = json.load(r)["hourly"]
        except Exception:  # noqa: BLE001 - daily cap or network; try again on a later run
            _WX_FAILED.add(loc)
            return None
        series = {"fetched_to": f"{end}T23:00", "i": {ts: i for i, ts in enumerate(h["time"])},
                  **{k: h[k] for k in ("temperature_2m", "wind_speed_10m", "wind_gusts_10m", "precipitation", "snowfall")}}
        _WX[loc] = series
        f.write_text(json.dumps(_WX))
    i = series["i"].get(hour)
    if i is None or series["temperature_2m"][i] is None:
        return None
    v = lambda k: sum((x or 0) for x in series[k][i:i + 4])  # noqa: E731 - over the ~4h game
    return {"temp": series["temperature_2m"][i], "wind": series["wind_speed_10m"][i],
            "gust": series["wind_gusts_10m"][i], "precip": v("precipitation"), "snow": v("snowfall")}


# ------------------------------------------------------------------------------------------
def build(league):
    games = load_games(league)
    box = nba_box if league == "nba" else nfl_box
    hl = 10 if league == "nba" else 5                # half-life (games) for season-long ratings
    hist = defaultdict(list)                          # team -> list of past team-game dicts
    last = {}                                         # team -> (time, place) of last game
    road = defaultdict(int)                           # consecutive road games
    elo = defaultdict(lambda: 1500.0)
    elo_seen = {}
    minutes_hist = defaultdict(lambda: defaultdict(deque))   # team -> player -> recent minutes / yards
    dnp_last = defaultdict(set)                       # team -> players who sat last game
    last_played = defaultdict(dict)                   # team -> player -> index of team game he last played
    league_tot = deque(maxlen=300)                    # recent game totals (for referee scoring tendency)
    ref_hist = defaultdict(list)                      # official -> [(home_won - expected), total_pts]
    mkt_resid = defaultdict(deque)                    # team -> recent (won - kalshi price) - filled by caller
    hfa = 70 if league == "nba" else 48
    rows = []
    for g in games:
        H, A = g["teams"]["home"], g["teams"]["away"]
        h, a = H["abbr"], A["abbr"]
        t = g["t"]
        # ---------------- venue
        if g.get("neutral") and g.get("city") in INTL:
            lat, lon = INTL[g["city"]]
            venue = {"lat": lat, "lon": lon, "elev": 50, "tz": round(lon / 15), "dome": False}
        else:
            venue = places.place(league, h) or {"lat": 0, "lon": 0, "elev": 0, "tz": -5, "dome": True}
        r = {"league": league, "id": g["id"], "date": g["date"], "start": g["start"], "home": h, "away": a,
             "season": g.get("season"), "season_type": g.get("season_type"), "week": (g.get("week") or {}).get("number") if isinstance(g.get("week"), dict) else g.get("week"),
             "home_score": H["score"], "away_score": A["score"], "home_win": 1 if H["score"] > A["score"] else 0 if H["score"] < A["score"] else None,
             "lines": g.get("lines") or []}
        # ---------------- ratings / style / form (home minus away)
        for side, team, opp in (("h", h, a), ("a", a, h)):
            hs = hist[team]
            r[f"{side}_games"] = len(hs)
            keys = hs[-1].keys() if hs else []
            for k in keys:
                if k in ("won", "margin", "t") or k.startswith("_"):
                    continue
                r[f"{side}_{k}"] = decayed_mean(hs, k, hl)
            r[f"{side}_win_pct"] = decayed_mean(hs, "won", hl)
            r[f"{side}_margin"] = decayed_mean(hs, "margin", hl)
            r[f"{side}_last5_win"] = sum(x["won"] for x in hs[-5:]) / max(1, len(hs[-5:])) if hs else None
            r[f"{side}_last5_margin"] = sum(x["margin"] for x in hs[-5:]) / max(1, len(hs[-5:])) if hs else None
            streak = 0
            for x in reversed(hs):
                if streak == 0:
                    streak = 1 if x["won"] else -1
                elif (x["won"] and streak > 0) or (not x["won"] and streak < 0):
                    streak += 1 if streak > 0 else -1
                else:
                    break
            r[f"{side}_streak"] = streak
            # schedule
            lt = last.get(team)
            here = venue
            rest = (t - lt[0]).total_seconds() / 86400 if lt else 7.0
            r[f"{side}_rest"] = min(rest, 10 if league == "nba" else 14)
            r[f"{side}_b2b"] = 1 if lt and rest < 1.6 else 0
            r[f"{side}_games_last4"] = sum(1 for x in hs if (t - x["t"]).days < 4)
            r[f"{side}_games_last7"] = sum(1 for x in hs if (t - x["t"]).days < 7)
            r[f"{side}_travel_km"] = places.km(lt[1], here) if lt else 0.0
            r[f"{side}_tz_shift"] = abs(here["tz"] - (lt[1]["tz"] if lt else here["tz"]))
            homeplace = places.place(league, team) or here
            r[f"{side}_tz_from_home"] = here["tz"] - homeplace["tz"]
            r[f"{side}_altitude_gain"] = max(0, here["elev"] - homeplace["elev"])
            r[f"{side}_road_trip"] = road[team] if side == "a" else 0
            local_hour = (t.hour + homeplace["tz"]) % 24   # kickoff/tip on the team's body clock
            r[f"{side}_body_clock_hour"] = local_hour
            # roster: regulars missing today, and regulars who missed the last game (known beforehand)
            mh = minutes_hist[team]
            n_team = len(hs)
            importance = {p: sum(v) / len(v) for p, v in mh.items()
                          if len(v) >= 2 and n_team - last_played[team].get(p, -99) <= 3   # played in one of the last 3 games
                          and (league == "nba" or sum(v) / len(v) >= 25)}                  # NFL: established skill players
            tot = sum(importance.values()) or 1.0
            played = {p["id"] for p in g["players"] if p["side"] == ("home" if side == "h" else "away") and not p.get("dnp") and _usage(league, p) > 0}
            out_today = [p for p, imp in importance.items() if p not in played and imp > 0]
            r[f"{side}_missing_share"] = sum(importance[p] for p in out_today) / tot
            r[f"{side}_missing_top_player"] = 1 if importance and max(importance, key=importance.get) in out_today else 0
            r[f"{side}_missed_last_share"] = sum(importance.get(p, 0) for p in dnp_last[team]) / tot
            if league == "nfl":
                qbs = [p for p in g["players"] if p["side"] == ("home" if side == "h" else "away") and p["group"] == "passing"]
                qb = max(qbs, key=lambda p: num(str(p["stats"].get("completions/passingAttempts", "0/0")).split("/")[-1]), default=None)
                prev_qb = hs[-1].get("_qb") if hs else None
                r[f"{side}_qb_change"] = 1 if qb and prev_qb and qb["id"] != prev_qb else 0
        r["elo_home_prob"] = elo_prob(elo[h] - elo[a] + (0 if g.get("neutral") else hfa))
        r["h_dome_team"] = 1 if (places.place(league, h) or {}).get("dome") else 0
        r["a_dome_team"] = 1 if (places.place(league, a) or {}).get("dome") else 0
        r["venue_dome"] = 1 if venue.get("dome") else 0
        r["neutral"] = 1 if g.get("neutral") else 0
        r["international"] = 1 if g.get("neutral") and g.get("city") in INTL else 0
        r["conference_game"] = 1 if g.get("conference_game") else 0
        r["playoffs"] = 1 if g.get("season_type") == 3 else 0
        r["preseason"] = 1 if g.get("season_type") == 1 else 0
        tv = set(g.get("tv") or [])
        r["national_tv"] = 1 if tv & NATIONAL_TV and (league == "nfl" or not tv & {"NBA League Pass"} or len(tv & NATIONAL_TV) > 0) else 0
        et_hour = (t.hour - 5) % 24
        r["start_hour_et"] = et_hour
        r["day_of_week"] = (t - timedelta(hours=5)).weekday()
        r["primetime"] = 1 if et_hour >= 19 or et_hour < 4 else 0
        r["month"] = (t - timedelta(hours=5)).month
        # officials' past tendencies
        offs = g.get("officials") or []
        crew = offs[:3] if league == "nba" else offs[:1]
        hb = [v for o in crew for v in ref_hist[o]]
        r["ref_home_bias"] = (sum(x[0] for x in hb) / (len(hb) + 30)) if hb else 0.0
        r["ref_total_bias"] = (sum(x[1] for x in hb) / (len(hb) + 30)) if hb else 0.0
        # weather (NFL outdoor)
        if league == "nfl" and not venue.get("dome"):
            w = weather(venue["lat"], venue["lon"], t)
            if w:
                r.update({"temp_f": w["temp"], "wind_mph": w["wind"], "gust_mph": w["gust"], "precip_mm": w["precip"], "snow_cm": w["snow"]})
        rows.append(r)

        # ---------------- update state with this game's results (AFTER the row is built)
        hw = 1.0 if H["score"] > A["score"] else 0.0 if H["score"] < A["score"] else 0.5
        exp = r["elo_home_prob"]
        mov = abs(H["score"] - A["score"])
        k = 20 if league == "nba" else 20
        for tm in (h, a):  # new season: regress a third to the mean
            if tm in elo_seen and (t - elo_seen[tm]).days > 90:
                elo[tm] = 1500 + (elo[tm] - 1500) * 0.67
            elo_seen[tm] = t
        delta = k * math.log(mov + 1) * (hw - exp)
        elo[h] += delta
        elo[a] -= delta
        for side, team, me, opp in (("home", h, H, A), ("away", a, A, H)):
            if not me.get("stats") or not opp.get("stats"):
                continue
            b = box(me, opp)
            b["won"] = 1 if me["score"] > opp["score"] else 0
            b["margin"] = me["score"] - opp["score"]
            b["t"] = t
            if league == "nfl":
                qbs = [p for p in g["players"] if p["side"] == side and p["group"] == "passing"]
                qb = max(qbs, key=lambda p: num(str(p["stats"].get("completions/passingAttempts", "0/0")).split("/")[-1]), default=None)
                b["_qb"] = qb["id"] if qb else None
            hist[team].append(b)
            if len(hist[team]) > 120:
                hist[team] = hist[team][-120:]
            last[team] = (t, venue)
            road[team] = road[team] + 1 if side == "away" else 0
            sat = set()
            mh = minutes_hist[team]
            for p in g["players"]:
                if p["side"] != side or not p.get("id"):
                    continue
                u = _usage(league, p)
                if p.get("dnp") or u == 0:
                    if p["id"] in mh:
                        sat.add(p["id"])
                    continue
                q = mh[p["id"]]
                q.append(u)
                last_played[team][p["id"]] = len(hist[team])
                if len(q) > 10:
                    q.popleft()
            dnp_last[team] = {x for x in sat if len(hist[team]) - last_played[team].get(x, -99) <= 3}
        tot_pts = H["score"] + A["score"]
        avg_tot = sum(league_tot) / len(league_tot) if league_tot else tot_pts
        for o in crew:
            ref_hist[o].append((hw - exp, tot_pts - avg_tot))
        league_tot.append(tot_pts)
    return rows


def _usage(league, p):
    st = p.get("stats") or {}
    if league == "nba":
        try:
            return float(st.get("minutes") or 0)
        except ValueError:
            return 0.0
    # offensive skill players only: defenders / linemen rarely show up in the box score, so their
    # "absence" can't be measured reliably
    return num(st.get("rushingYards")) + num(st.get("receivingYards")) + num(st.get("passingYards")) / 3


# ------------------------------------------------------------------------------------------
# Kalshi prices
def kalshi_game_prices(league):
    """(date, team) -> candle history of the Kalshi game-winner market for that team."""
    series = "KXNBAGAME" if league == "nba" else "KXNFLGAME"
    f = DATA / f"kalshi_{series}.jsonl.gz"
    out = {}
    if not f.exists():
        return out
    alias = places.KALSHI_ALIAS[league]
    with gzip.open(f, "rt") as fh:
        for line in fh:
            m = json.loads(line)
            code = m["ticker"].rsplit("-", 1)[-1]
            out[(m["event_ticker"].split("-")[1][:7], alias.get(code, code))] = m
    return out


def snapshot(candles, at_ts):
    best = None
    for ts, bid, ask, vol, oi in candles:
        if ts <= at_ts and bid is not None and ask is not None and 0 < bid <= ask < 1:
            best = (bid, ask, oi)
    return best


def attach_market(rows, league):
    px = kalshi_game_prices(league)
    mon = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()
    for r in rows:
        t = parse_ts(r["start"])
        local = t - timedelta(hours=5)
        for d in (local, local - timedelta(days=1), local + timedelta(days=1)):
            key = f"{d:%y}{mon[d.month - 1]}{d:%d}"
            m = px.get((key, r["home"])) or px.get((key, r["away"]))
            if m:
                break
        if not m:
            continue
        flip = px.get((key, r["home"])) is None   # market is on the away team
        cs = m["candles"]
        ts0 = t.timestamp()
        q3, q1 = snapshot(cs, ts0 - 3 * 3600), snapshot(cs, ts0 - 3600)
        q0 = next(((b, a) for _, b, a, _, _ in cs if b is not None and a is not None and 0 < b <= a < 1), None)
        if not q3:
            continue
        mid = lambda q: (q[0] + q[1]) / 2  # noqa: E731
        conv = (lambda p: 1 - p) if flip else (lambda p: p)
        r["kalshi_home_3h"] = conv(mid(q3))
        r["kalshi_spread_3h"] = q3[1] - q3[0]
        r["kalshi_oi_3h"] = q3[2] or 0
        r["kalshi_home_1h"] = conv(mid(q1)) if q1 else r["kalshi_home_3h"]
        r["kalshi_home_open"] = conv(mid(q0)) if q0 else r["kalshi_home_3h"]
        r["kalshi_result_home"] = (1 if m["result"] == "yes" else 0) if not flip else (0 if m["result"] == "yes" else 1)
    return rows


def sportsbook_home_prob(r, league):
    for ln in r.get("lines") or []:
        hm, am = ln.get("home_ml"), ln.get("away_ml")
        if hm and am:
            imp = lambda o: (100 / (o + 100)) if o > 0 else (-o / (-o + 100))  # noqa: E731
            ph, pa = imp(hm), imp(am)
            return ph / (ph + pa)
        if ln.get("spread") is not None:
            sd = 12.5 if league == "nba" else 13.5
            return 0.5 * (1 + math.erf((-float(ln["spread"]) / sd) / math.sqrt(2)))
    return None
