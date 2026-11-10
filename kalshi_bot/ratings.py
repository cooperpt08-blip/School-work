"""ESPN results -> Elo team ratings, used as a second opinion on Kalshi game-winner markets.

Elo only needs final scores, so the same code covers every league ESPN publishes. The learner
decides (per league) how much weight these ratings get versus the Kalshi price; if the ratings
don't help in a league, they get ~zero weight there automatically.
"""
import csv
import json
import math
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from . import config

# Kalshi game-winner series -> (ESPN path, extra query, Elo K, home advantage in Elo points)
LEAGUES = {
    "KXNFLGAME": ("football/nfl", "", 20, 48),
    "KXNBAGAME": ("basketball/nba", "", 20, 70),
    "KXNHLGAME": ("hockey/nhl", "", 10, 30),
    "KXMLBGAME": ("baseball/mlb", "", 5, 24),
    "KXWNBAGAME": ("basketball/wnba", "", 20, 60),
    "KXNCAAFGAME": ("football/college-football", "&groups=80", 25, 60),
    "KXNCAAMBGAME": ("basketball/mens-college-basketball", "&groups=50", 22, 85),
    "KXNCAAWBGAME": ("basketball/womens-college-basketball", "&groups=50", 22, 70),
}
FIELDS = ["date", "start", "event_id", "state", "home_id", "home", "home_abbr", "home_loc", "home_score",
          "away_id", "away", "away_abbr", "away_loc", "away_score", "neutral"]
HISTORY_DAYS = 420  # one full season back, so ratings carry over between seasons


def _fetch_day(path, extra, d):
    url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard?dates={d:%Y%m%d}&limit=1000{extra}"
    # Note: ESPN answers 403 to custom User-Agent strings, so use urllib's default.
    err = None
    for i in range(4):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.load(r).get("events") or []
        except urllib.error.HTTPError as e:
            err = e
            if e.code in (400, 403, 404):
                break
            time.sleep(2 * (i + 1))
        except Exception as e:  # noqa: BLE001 - network hiccup, retry
            err = e
            time.sleep(2 * (i + 1))
    print(f"    ESPN fetch failed for {path} {d}: {err!r}", flush=True)
    return None


def _rows(events, d):
    for ev in events:
        comp = (ev.get("competitions") or [{}])[0]
        sides = {c.get("homeAway"): c for c in comp.get("competitors") or []}
        if "home" not in sides or "away" not in sides:
            continue
        row = {"date": d.isoformat(), "start": ev.get("date", ""), "event_id": ev.get("id", ""),
               "state": ((comp.get("status") or {}).get("type") or {}).get("state", ""),
               "neutral": int(bool(comp.get("neutralSite")))}
        for side in ("home", "away"):
            t = sides[side].get("team") or {}
            row.update({f"{side}_id": t.get("id", ""), side: t.get("displayName", ""),
                        f"{side}_abbr": t.get("abbreviation", ""), f"{side}_loc": t.get("location", ""),
                        f"{side}_score": sides[side].get("score", "")})
        yield row


def update_games(series=None, today=None, log=print):
    """Keep data/games/<series>.csv current: full history once, then just the recent/upcoming days."""
    config.GAMES.mkdir(parents=True, exist_ok=True)
    today = today or datetime.now(timezone.utc).date()
    for s, (path, extra, _, _) in LEAGUES.items():
        if series and s not in series:
            continue
        f = config.GAMES / f"{s}.csv"
        rows = {}
        if f.exists():
            with open(f, newline="") as fh:
                for r in csv.DictReader(fh):
                    rows[(r["date"], r["event_id"])] = r
            done = {r["date"] for r in rows.values()}
            start = today - timedelta(days=4)
            # fill any gaps (e.g. if the workflow didn't run for a while)
            last = max(done) if done else None
            if last and date.fromisoformat(last) < start:
                start = date.fromisoformat(last) - timedelta(days=1)
        else:
            start = today - timedelta(days=HISTORY_DAYS)
        end = today + timedelta(days=3)
        days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        log(f"  ESPN {s}: {len(days)} days")
        with ThreadPoolExecutor(max_workers=8) as pool:
            fetched = list(pool.map(lambda d: (d, _fetch_day(path, extra, d)), days))
        for d, evs in fetched:
            if evs is None:
                continue
            for k in [k for k in rows if k[0] == d.isoformat()]:
                del rows[k]
            for r in _rows(evs, d):
                rows[(r["date"], r["event_id"])] = r
        with open(f, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            w.writeheader()
            for k in sorted(rows):
                w.writerow({k2: rows[k].get(k2, "") for k2 in FIELDS})


def load_games(series):
    f = config.GAMES / f"{series}.csv"
    if not f.exists():
        return []
    with open(f, newline="") as fh:
        return sorted(csv.DictReader(fh), key=lambda r: (r["start"], r["event_id"]))


def elo_prob(diff):
    return 1.0 / (1.0 + 10 ** (-diff / 400.0))


class Elo:
    """Replays a league's results in order. pregame[event_id] = P(home wins) using only earlier games."""

    def __init__(self, series):
        _, _, self.k, self.hfa = LEAGUES[series]
        self.r, self.last = {}, {}
        self.pregame, self.games = {}, {}
        for g in load_games(series):
            self.games[g["event_id"]] = g
            h, a = g["home_id"], g["away_id"]
            when = g["start"][:10] or g["date"]
            for t in (h, a):
                self._season_reset(t, when)
            hfa = 0 if g.get("neutral") == "1" else self.hfa
            diff = self.r.get(h, 1500) - self.r.get(a, 1500) + hfa
            self.pregame[g["event_id"]] = elo_prob(diff)
            if g["state"] != "post":
                continue
            try:
                hs, as_ = float(g["home_score"]), float(g["away_score"])
            except ValueError:
                continue
            res = 1.0 if hs > as_ else 0.0 if hs < as_ else 0.5
            mov = abs(hs - as_)
            mult = math.log(mov + 1) * 2.2 / ((abs(diff) * 0.001) + 2.2) if mov else 1.0
            delta = self.k * mult * (res - elo_prob(diff))
            self.r[h] = self.r.get(h, 1500) + delta
            self.r[a] = self.r.get(a, 1500) - delta
            self.last[h] = self.last[a] = when

    def _season_reset(self, team, when):
        prev = self.last.get(team)
        if prev and (date.fromisoformat(when) - date.fromisoformat(prev)).days > 75:
            self.r[team] = 1500 + (self.r.get(team, 1500) - 1500) * 0.67


# ---------------------------------------------------------------------------------------
# Matching a Kalshi market ("Cleveland wins", event "Cleveland vs Charlotte") to an ESPN game
_MONTHS = {m: i for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split(), 1)}


def _norm(s):
    s = (s or "").lower().replace("&", "and")
    s = re.sub(r"\bst\.?(?=\s|$)", "state", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"^la(?= |$)", "los angeles", " ".join(s.split()))


def _team_match(name, g, side):
    loc, full = _norm(g[f"{side}_loc"]), _norm(g[side])
    # Kalshi disambiguates shared cities with a letter: "Los Angeles C" = Clippers, "New York J" = Jets
    m = re.match(r"^(.+) ([A-Za-z])$", (name or "").strip())
    if m and len(m.group(1)) > 2:
        city, letter = _norm(m.group(1)), m.group(2).lower()
        nickname = full[len(loc):].strip() if loc and full.startswith(loc) else ""
        return 3 if city == loc and nickname.startswith(letter) else 0
    n = _norm(name)
    if not n:
        return 0
    cands = [loc, full, _norm(g[f"{side}_abbr"])]
    if n in cands:
        return 3
    if any(c and (c.startswith(n) or n.startswith(c)) for c in cands[:2]):
        return 2
    return 0


def event_date(event_ticker):
    m = re.search(r"-(\d\d)([A-Z]{3})(\d\d)", event_ticker or "")
    if not m or m.group(2) not in _MONTHS:
        return None
    return date(2000 + int(m.group(1)), _MONTHS[m.group(2)], int(m.group(3)))


class Matcher:
    def __init__(self):
        self.elo = {}
        self.by_date = {}

    def _league(self, series):
        if series not in self.elo:
            e = Elo(series) if (config.GAMES / f"{series}.csv").exists() else None
            self.elo[series] = e
            idx = {}
            if e:
                for g in e.games.values():
                    idx.setdefault(g["date"], []).append(g)
            self.by_date[series] = idx
        return self.elo[series]

    def game_prob(self, series, event_ticker, event_title, yes_team):
        """-> (P(yes team wins) per Elo, espn game row) or (None, None)."""
        if series not in LEAGUES:
            return None, None
        elo = self._league(series)
        d = event_date(event_ticker)
        if not elo or not d:
            return None, None
        names = re.split(r"\s+(?:vs\.?|at|@)\s+", event_title or "")
        if len(names) != 2:
            return None, None
        best, best_score = None, 0
        for day in (d, d - timedelta(days=1), d + timedelta(days=1)):
            for g in self.by_date[series].get(day.isoformat(), []):
                s1 = max(_team_match(names[0], g, "home") + _team_match(names[1], g, "away"),
                         _team_match(names[0], g, "away") + _team_match(names[1], g, "home"))
                if s1 > best_score:
                    best, best_score = g, s1
            if best_score >= 4:
                break
        if not best or best_score < 4:
            return None, None
        p_home = elo.pregame.get(best["event_id"])
        if p_home is None:
            return None, None
        yh, ya = _team_match(yes_team, best, "home"), _team_match(yes_team, best, "away")
        if yh == ya:
            return None, None
        return (p_home if yh > ya else 1 - p_home), best
