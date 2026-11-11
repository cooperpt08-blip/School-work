"""Pre-game research dossier for tonight's NBA games: python -m kalshi_bot.research.dossier 20261111

Builds every pre-game factor for UPCOMING games the same way the research did for past games
(by appending tonight's games as stubs after all completed games), plus ESPN's current injury
report and Kalshi's line. Output: data/dossier_<date>.json and a printed summary."""
import copy
import json
import sys
import urllib.request
from datetime import datetime, timezone

from .. import kalshi
from . import features as F
from . import places

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"


def get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def upcoming(day):
    out = []
    for ev in get(f"{BASE}/scoreboard?dates={day}").get("events", []):
        c = ev["competitions"][0]
        if c["status"]["type"]["state"] != "pre":
            continue
        t = {x["homeAway"]: x for x in c["competitors"]}
        s = get(f"{BASE}/summary?event={ev['id']}")
        inj = {}
        for team in s.get("injuries") or []:
            inj[team["team"]["abbreviation"]] = [(i["athlete"]["displayName"], i.get("status"), (i.get("details") or {}).get("type"))
                                                 for i in team.get("injuries", [])]
        out.append({"id": ev["id"], "date": f"{day[:4]}-{day[4:6]}-{day[6:]}", "start": ev["date"],
                    "season": ev.get("season", {}).get("year"), "season_type": 2, "neutral": bool(c.get("neutralSite")),
                    "conference_game": bool(c.get("conferenceCompetition")), "city": None, "officials": [], "tv": [], "lines": [],
                    "teams": {side: {"abbr": t[side]["team"]["abbreviation"], "name": t[side]["team"]["displayName"],
                                     "score": 0.0, "record": [(t[side].get("records") or [{}])[0].get("summary")]}
                              for side in ("home", "away")},
                    "players": [], "injuries": inj, "_stub": True})
    return out


def kalshi_lines(day_code):
    lines = {}
    alias = places.KALSHI_ALIAS["nba"]
    for e in kalshi.paged("/events", "events", {"series_ticker": "KXNBAGAME", "status": "open", "with_nested_markets": "true", "limit": 200}):
        if day_code not in e["event_ticker"]:
            continue
        for m in e.get("markets") or []:
            code = m["ticker"].rsplit("-", 1)[-1]
            bid, ask = kalshi.dollars(m.get("yes_bid_dollars")), kalshi.dollars(m.get("yes_ask_dollars"))
            lines[alias.get(code, code)] = (bid, ask)
    return lines


def build(day):
    stubs = upcoming(day)
    real = F.load_games("nba")
    orig = F.load_games
    for g in stubs:
        g["t"] = F.parse_ts(g["start"])
    F.load_games = lambda league: real + copy.deepcopy(stubs)
    try:
        rows = F.build("nba")
    finally:
        F.load_games = orig
    rows = {r["id"]: r for r in rows if r["id"] in {g["id"] for g in stubs}}
    mon = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()
    d = datetime.strptime(day, "%Y%m%d")
    kl = kalshi_lines(f"{d:%y}{mon[d.month - 1]}{d:%d}")
    out = []
    for g in stubs:
        r = rows[g["id"]]
        h, a = g["teams"]["home"]["abbr"], g["teams"]["away"]["abbr"]
        k = kl.get(h)
        r["kalshi_home"] = (k[0] + k[1]) / 2 if k and k[0] is not None and k[1] is not None else None
        r["kalshi_home_ask"] = k[1] if k else None
        ka = kl.get(a)
        r["kalshi_away_ask"] = ka[1] if ka else None
        r["injuries"] = g["injuries"]
        r["records"] = {h: g["teams"]["home"]["record"][0], a: g["teams"]["away"]["record"][0]}
        out.append(r)
    return out


def main(day):
    rows = build(day)
    keep = ["home", "away", "records", "kalshi_home", "kalshi_home_ask", "kalshi_away_ask", "elo_home_prob",
            "h_off_rtg", "h_def_rtg", "a_off_rtg", "a_def_rtg", "h_pace", "a_pace", "h_margin", "a_margin",
            "h_last5_win", "a_last5_win", "h_last5_margin", "a_last5_margin", "h_streak", "a_streak",
            "h_rest", "a_rest", "h_b2b", "a_b2b", "h_games_last7", "a_games_last7", "a_travel_km", "a_tz_shift",
            "a_road_trip", "h_three_rate", "a_three_rate", "h_three_pct", "a_three_pct", "h_opp_three_pct", "a_opp_three_pct",
            "h_rim_share", "a_rim_share", "h_opp_rim_fg", "a_opp_rim_fg", "h_tov_pct", "a_tov_pct", "h_oreb_pct", "a_oreb_pct",
            "injuries", "start"]
    slim = [{k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items() if k in keep} for r in rows]
    (F.DATA / f"dossier_{day}.json").write_text(json.dumps(slim, indent=1))
    for r in slim:
        print(json.dumps(r))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else datetime.now(timezone.utc).strftime("%Y%m%d"))
