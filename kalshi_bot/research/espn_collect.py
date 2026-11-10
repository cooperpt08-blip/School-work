"""Download every NBA / NFL game since Sep 2024 from ESPN and keep a compact record of it.

Per game: teams, score, start time, venue (city, indoor), neutral site, season type/week,
officials, TV, sportsbook line (ESPN pickcenter), both teams' box-score stats, every player's
stat line (incl. who didn't play and why), and a play-type profile from the play-by-play.

Output: research/data/<league>_games.jsonl.gz (one JSON object per game). Resumable.
"""
import gzip
import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent / "data"
OUT.mkdir(parents=True, exist_ok=True)
LEAGUES = {"nba": "basketball/nba", "nfl": "football/nfl"}
START = {"nba": date(2024, 10, 1), "nfl": date(2024, 8, 1)}
BASE = "https://site.api.espn.com/apis/site/v2/sports"


def get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=40) as r:  # ESPN 403s custom User-Agents
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (400, 403, 404):
                return None
            time.sleep(2 * (i + 1))
        except Exception:  # noqa: BLE001
            time.sleep(2 * (i + 1))
    return None


def event_ids(league, end, start=None):
    ids = []
    start = start or START[league]
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    with ThreadPoolExecutor(8) as pool:
        for d, sb in zip(days, pool.map(lambda d: get(f"{BASE}/{LEAGUES[league]}/scoreboard?dates={d:%Y%m%d}&limit=1000"), days)):
            for ev in (sb or {}).get("events", []):
                st = ((ev.get("competitions") or [{}])[0].get("status") or {}).get("type") or {}
                if st.get("completed"):
                    ids.append((d.isoformat(), ev["id"]))
    return ids


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _pair(v, sep="-"):
    try:
        a, b = str(v).replace("/", sep).split(sep)[:2]
        return float(a), float(b)
    except ValueError:
        return None, None


def team_stats(stats):
    out = {}
    for s in stats or []:
        name, val = s.get("name"), s.get("displayValue")
        if name is None:
            continue
        if "-" in name or name in ("thirdDownEff", "fourthDownEff", "redZoneAttempts", "sacksYardsLost",
                                   "totalPenaltiesYards", "completionAttempts"):
            a, b = _pair(val)
            out[name + "_a"], out[name + "_b"] = a, b
        elif name == "possessionTime":
            try:
                m, s_ = val.split(":")
                out[name] = int(m) + int(s_) / 60
            except ValueError:
                pass
        else:
            out[name] = _num(val)
    return out


def play_profile(plays, home_id, away_id):
    """NBA shot profile per team from play-by-play text."""
    prof = {home_id: {}, away_id: {}}
    for p in plays or []:
        tid = (p.get("team") or {}).get("id")
        if tid not in prof or not p.get("shootingPlay"):
            continue
        txt = ((p.get("type") or {}).get("text") or "").lower()
        if "free throw" in txt:
            continue
        kind = ("three" if (p.get("scoreValue") == 3 or "three point" in (p.get("text") or "").lower()) else
                "rim" if any(k in txt for k in ("layup", "dunk", "tip", "alley")) else
                "midrange" if "jump" in txt or "fade" in txt or "hook" in txt else "other")
        d = prof[tid]
        d[kind + "_att"] = d.get(kind + "_att", 0) + 1
        if p.get("scoringPlay"):
            d[kind + "_made"] = d.get(kind + "_made", 0) + 1
        if "pullup" in txt or "step back" in txt:
            d["pullup_att"] = d.get("pullup_att", 0) + 1
        if "driving" in txt or "cutting" in txt:
            d["drive_att"] = d.get("drive_att", 0) + 1
    return prof


def compact(league, day, eid):
    s = get(f"{BASE}/{LEAGUES[league]}/summary?event={eid}")
    if not s:
        return None
    comp = ((s.get("header") or {}).get("competitions") or [{}])[0]
    sides = {c.get("homeAway"): c for c in comp.get("competitors") or []}
    if "home" not in sides or "away" not in sides:
        return None
    gi = s.get("gameInfo") or {}
    venue = gi.get("venue") or {}
    g = {"league": league, "date": day, "id": eid, "start": comp.get("date"),
         "season": ((s.get("header") or {}).get("season") or {}).get("year"),
         "season_type": ((s.get("header") or {}).get("season") or {}).get("type"),
         "week": (s.get("header") or {}).get("week"),
         "neutral": bool(comp.get("neutralSite")), "conference_game": bool(comp.get("conferenceCompetition")),
         "venue": venue.get("fullName"), "city": (venue.get("address") or {}).get("city"),
         "state": (venue.get("address") or {}).get("state"), "indoor": venue.get("indoor"), "grass": venue.get("grass"),
         "weather": gi.get("weather"), "officials": [o.get("displayName") for o in gi.get("officials") or []],
         "tv": sorted({n for b in comp.get("broadcasts") or [] for n in ((b.get("media") or {}).get("shortName"),) if n}),
         "lines": [{"provider": (p.get("provider") or {}).get("name"), "spread": p.get("spread"),
                    "total": p.get("overUnder"),
                    "home_ml": ((p.get("homeTeamOdds") or {}).get("moneyLine")),
                    "away_ml": ((p.get("awayTeamOdds") or {}).get("moneyLine")),
                    "home_fav": (p.get("homeTeamOdds") or {}).get("favorite")} for p in s.get("pickcenter") or []],
         "teams": {}}
    ids = {}
    for side in ("home", "away"):
        c = sides[side]
        t = c.get("team") or {}
        ids[side] = t.get("id")
        g["teams"][side] = {"id": t.get("id"), "abbr": t.get("abbreviation"), "name": t.get("displayName"),
                            "score": _num(c.get("score")), "winner": c.get("winner"),
                            "linescores": [_num(x.get("displayValue")) for x in c.get("linescores") or []],
                            "record": [r.get("summary") for r in c.get("record") or []][:1]}
    for bt in (s.get("boxscore") or {}).get("teams") or []:
        tid = (bt.get("team") or {}).get("id")
        for side in ("home", "away"):
            if ids[side] == tid:
                g["teams"][side]["stats"] = team_stats(bt.get("statistics"))
    players = []
    for bp in (s.get("boxscore") or {}).get("players") or []:
        tid = (bp.get("team") or {}).get("id")
        side = "home" if tid == ids["home"] else "away"
        for grp in bp.get("statistics") or []:
            keys = grp.get("keys") or grp.get("names") or []
            for a in grp.get("athletes") or []:
                ath = a.get("athlete") or {}
                players.append({"side": side, "group": grp.get("name") or grp.get("type"), "id": ath.get("id"),
                                "name": ath.get("displayName"), "pos": (ath.get("position") or {}).get("abbreviation"),
                                "starter": a.get("starter"), "dnp": a.get("didNotPlay"), "reason": a.get("reason"),
                                "stats": dict(zip(keys, a.get("stats") or []))})
    g["players"] = players
    if league == "nba":
        prof = play_profile(s.get("plays"), ids["home"], ids["away"])
        for side in ("home", "away"):
            g["teams"][side]["shots"] = prof.get(ids[side], {})
    return g


def collect(league):
    f = OUT / f"{league}_games.jsonl.gz"
    have = set()
    if f.exists():
        with gzip.open(f, "rt") as fh:
            have = {json.loads(line)["id"] for line in fh}
    # first run: full history; afterwards only the last 10 days need checking for new games
    start = date.today() - timedelta(days=10) if have else None
    ids = [(d, e) for d, e in event_ids(league, date.today(), start) if e not in have]
    print(f"{league}: {len(have)} already saved, {len(ids)} to fetch", flush=True)
    done = 0
    with ThreadPoolExecutor(8) as pool, gzip.open(f, "at") as fh:
        for g in pool.map(lambda de: compact(league, *de), ids):
            done += 1
            if g:
                fh.write(json.dumps(g, separators=(",", ":")) + "\n")
            if done % 250 == 0:
                print(f"  {league} {done}/{len(ids)}", flush=True)


if __name__ == "__main__":
    for lg in sys.argv[1:] or LEAGUES:
        collect(lg)
