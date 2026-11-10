"""Grade the old bot's emailed picks against real final scores (ESPN scoreboards)."""
import csv, json, re, sys, time, urllib.request
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).parent
CACHE = Path("/tmp/espn_cache")
CACHE.mkdir(exist_ok=True)
LEAGUE = {"MLB": "baseball/mlb", "WNBA": "basketball/wnba", "MLS": "soccer/usa.1", "FIFA": "soccer/fifa.world"}


def scoreboard(sport, day):
    f = CACHE / f"{sport}_{day:%Y%m%d}.json"
    if not f.exists():
        url = f"https://site.api.espn.com/apis/site/v2/sports/{LEAGUE[sport]}/scoreboard?dates={day:%Y%m%d}&limit=200"
        for i in range(3):
            try:
                f.write_bytes(urllib.request.urlopen(url, timeout=30).read())
                break
            except Exception as e:  # noqa
                time.sleep(2 * (i + 1))
        else:
            return []
    return json.loads(f.read_text()).get("events", [])


def norm(s):
    s = s.lower().replace("athletics athletics", "athletics")
    return set(re.sub(r"[^a-z0-9 ]", " ", s).split()) - {"fc", "sc", "cf", "the", "city"} or set(s.split())


def same_team(a, b):
    na, nb = norm(a), norm(b)
    return bool(na & nb) and (na <= nb or nb <= na or len(na & nb) >= 2)


def find_game(sport, away, home, gt):
    # emailed time is local; a 12:xx AM start usually belongs to the previous evening's slate
    base = gt.date()
    days = [base, base - timedelta(days=1), base + timedelta(days=1)]
    cands = []
    for d in days:
        for ev in scoreboard(sport, datetime(d.year, d.month, d.day)):
            comp = ev["competitions"][0]
            teams = {c["homeAway"]: c for c in comp["competitors"]}
            if "home" not in teams or "away" not in teams:
                continue
            h, a = teams["home"]["team"]["displayName"], teams["away"]["team"]["displayName"]
            if same_team(home, h) and same_team(away, a) or same_team(home, a) and same_team(away, h):
                if not comp["status"]["type"].get("completed"):
                    continue
                start = datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).replace(tzinfo=None)
                cands.append((abs((start - (gt + timedelta(hours=1))).total_seconds()), ev, teams))
        if cands:
            break
    if not cands:
        return None
    _, ev, teams = min(cands, key=lambda c: c[0])
    return {side: (c["team"]["displayName"], float(c.get("score", 0) or 0)) for side, c in teams.items()}


def grade(row, g):
    (hn, hs), (an, as_) = g["home"], g["away"]
    sel, typ = row["selection"], row["type"]
    if typ == "Total":
        m = re.match(r"(Over|Under) ([\d.]+)", sel)
        tot = hs + as_
        return (tot > float(m[2])) if m[1] == "Over" else (tot < float(m[2]))
    team = re.sub(r" wins by.*", "", sel)
    mine, theirs = (hs, as_) if same_team(team, hn) else (as_, hs)
    if typ == "Spread":
        need = float(re.search(r"wins by ([\d.]+)", sel)[1])
        return mine - theirs > need
    return mine > theirs  # moneyline; soccer draw = loss


def main():
    rows = []
    for line in (HERE / "old_picks_from_emails.psv").read_text().splitlines():
        sent, sport, typ, matchup, sel, gtime, model, kalshi, edge = line.split("|")
        sentdt = datetime.fromisoformat(sent)
        gt = datetime.strptime(f"{gtime} {sentdt.year}", "%a %b %d, %I:%M %p %Y")
        rows.append(dict(sent=sent, sport=sport, type=typ, matchup=matchup, selection=sel, game_time=gt,
                         model=float(model) / 100, kalshi=float(kalshi) / 100, edge=float(edge) / 100))
    # one bet per (game, selection): keep the FIRST time the bot recommended it
    seen, picks = set(), []
    for r in sorted(rows, key=lambda r: r["sent"]):
        k = (r["sport"], r["type"], r["matchup"], r["selection"], r["game_time"])
        if k not in seen:
            seen.add(k)
            picks.append(r)
    out = []
    for r in picks:
        away, home = r["matchup"].split(" at ")
        g = find_game(r["sport"], away, home, r["game_time"])
        r["result"] = "" if g is None else ("W" if grade(r, g) else "L")
        r["score"] = "" if g is None else f'{g["away"][0]} {g["away"][1]:g} @ {g["home"][0]} {g["home"][1]:g}'
        out.append(r)
    with open(HERE / "old_picks_graded.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    print(f"{len(rows)} rows -> {len(picks)} unique picks; ungraded: {sum(1 for r in out if not r['result'])}")
    for r in out:
        if not r["result"]:
            print("  UNGRADED", r["sport"], r["matchup"], r["game_time"])


if __name__ == "__main__":
    main()
