"""Spreads and totals: does anything predict covering / going over beyond Kalshi's price?

python -m kalshi_bot.research.run_lines nba|nfl
"""
import gzip
import json
import math
import re
import sys
from datetime import timedelta

from . import analysis as A
from . import features as F
from . import places

MON = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()


def load(series):
    f = F.DATA / f"kalshi_{series}.jsonl.gz"
    out = []
    try:
        with gzip.open(f, "rt") as fh:
            for line in fh:
                out.append(json.loads(line))
    except (EOFError, OSError):
        pass  # file still being written - use what is complete
    return out


def run(league):
    rows = F.attach_market(F.build(league), league)
    rows = [r for r in rows if r.get("home_win") is not None and not r.get("preseason")]
    D = A.derive(rows, league)
    rev = {v: k for k, v in places.KALSHI_ALIAS[league].items()}  # ESPN abbr -> Kalshi code
    by_key = {}
    for d in D:
        r = d["row"]
        t = F.parse_ts(r["start"]) - timedelta(hours=5)
        for day in (t, t - timedelta(days=1), t + timedelta(days=1)):
            code = f"{day:%y}{MON[day.month - 1]}{day:%d}"
            by_key.setdefault(code, []).append(d)
    pre = "NBA" if league == "nba" else "NFL"
    sd_total, sd_margin = (18.0, 12.5) if league == "nba" else (13.5, 13.5)
    out = {}
    for kind in ("SPREAD", "TOTAL"):
        data = []
        for m in load(f"KX{pre}{kind}"):
            if m.get("result") not in ("yes", "no") or m.get("floor_strike") is None:
                continue
            ev = m["event_ticker"].split("-")[1]
            code, teams = ev[:7], ev[7:]
            cands = [d for d in by_key.get(code, [])
                     if rev.get(d["row"]["home"], d["row"]["home"]) in teams and rev.get(d["row"]["away"], d["row"]["away"]) in teams]
            if len(cands) != 1:
                continue
            d = cands[0]
            r, x0 = d["row"], d["x"]
            t0 = F.parse_ts(r["start"]).timestamp()
            q = F.snapshot(m["candles"], t0 - 3 * 3600)
            if not q:
                continue
            p = (q[0] + q[1]) / 2
            strike = float(m["floor_strike"])
            g = lambda k: r.get(k) or 0.0  # noqa: E731
            if kind == "TOTAL":
                if league == "nba":
                    pace = (g("h_pace") + g("a_pace")) / 2
                    proj = pace * (g("h_off_rtg") + g("a_def_rtg") + g("a_off_rtg") + g("h_def_rtg")) / 200
                else:
                    proj = (g("h_pts") + g("a_opp_pts") + g("a_pts") + g("h_opp_pts")) / 2
                book = next((ln.get("total") for ln in r["lines"] if ln.get("total")), None)
                x = {"proj_cushion": (proj - strike) / sd_total,
                     "ref_total_bias": x0.get("ctx_ref_total_bias", 0),
                     "pace_sum": (g("h_pace") + g("a_pace")) if league == "nba" else (g("h_plays") + g("a_plays")),
                     "both_b2b": g("h_b2b") + g("a_b2b"), "rest_sum": g("h_rest") + g("a_rest"),
                     "missing_sum": g("h_missing_share") + g("a_missing_share"),
                     "missed_last_sum": g("h_missed_last_share") + g("a_missed_last_share"),
                     "three_rate_sum": g("h_three_rate") + g("a_three_rate"),
                     "altitude": 1 if r["home"] in ("DEN", "UTAH") else 0,
                     "national_tv": r.get("national_tv", 0), "playoffs": r.get("playoffs", 0)}
                if book:
                    x["book_cushion"] = (float(book) - strike) / sd_total
                if league == "nfl":
                    x["dome"] = r.get("venue_dome", 0)
                    if "temp_f" in r:
                        x.update({"wind": r["wind_mph"], "temp": r["temp_f"], "rain_snow": 1 if (r["precip_mm"] > 1 or r["snow_cm"] > 0) else 0})
            else:
                code_t = re.match(r"([A-Z]+)", m["ticker"].rsplit("-", 1)[-1]).group(1)
                team = places.KALSHI_ALIAS[league].get(code_t, code_t)
                if team not in (r["home"], r["away"]):
                    continue
                s = 1 if team == r["home"] else -1
                hfa = 2.5 if league == "nba" else 1.8
                proj = s * ((g("h_margin") - g("a_margin")) / 2 + (0 if r.get("neutral") else hfa))
                book = next((ln.get("spread") for ln in r["lines"] if ln.get("spread") is not None), None)
                x = {"proj_cushion": (proj - strike) / sd_margin,
                     "kalshi_win_prob_logit": s * A.logit(r["kalshi_home_3h"]) if "kalshi_home_3h" in r else 0}
                if book is not None:
                    x["book_cushion"] = (s * -float(book) - strike) / sd_margin
                for k, v in x0.items():  # every team factor, oriented to the team named in the market
                    if k.startswith(("diff_", "mu_")) or k in ("elo_vs_market", "sportsbook_vs_kalshi", "mkt_resid_momentum"):
                        x[k] = s * v
            data.append({"x": x, "y": 1 if m["result"] == "yes" else 0, "p": p, "date": r["date"]})
        data.sort(key=lambda d: d["date"])
        if len(data) < 150:
            print(f"{league} {kind}: only {len(data)} matched markets - skipping")
            continue
        res = A.test_all(data)
        k = int(len(data) * 0.7)
        chosen = [r_["factor"] for r_ in sorted(A.test_all(data[:k]), key=lambda r_: -abs(r_["mkt_z"])) if abs(r_["mkt_z"]) >= 2.5][:6]
        wf = A.walk_forward(data, chosen)
        print(f"\n{league.upper()} {kind}S: {len(data)} priced markets, hit {sum(d['y'] for d in data) / len(data):.3f} vs price {sum(d['p'] for d in data) / len(data):.3f}")
        for r_ in sorted(res, key=lambda r_: r_["mkt_q"])[:14]:
            flag = "  <== beats price" if r_["mkt_q"] < 0.10 else ""
            print(f"   {r_['factor']:<32} n={r_['n']:<5} raw z {r_['raw_z']:+5.1f}   beyond price {r_['mkt_b'] * 25:+5.1f}%  z {r_['mkt_z']:+5.1f}  q {r_['mkt_q']:.3f}{flag}")
        print("   walk-forward (chosen on older 70%):", chosen, {k2: round(v, 4) for k2, v in (wf or {}).items() if k2 in ("gain", "z", "n_test")})
        out[kind] = {"results": res, "walk_forward": wf}
    json.dump(out, open(F.DATA / f"results_{league}_lines.json", "w"), indent=1, default=str)


if __name__ == "__main__":
    run(sys.argv[1])
