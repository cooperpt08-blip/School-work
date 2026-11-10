"""Test every pre-game factor two ways:
  RAW            does it predict the winner on its own?
  BEYOND MARKET  does it predict the winner after accounting for Kalshi's price 3h before? (only this can make money)
Multiple-testing control: Benjamini-Hochberg q-values across all factors in a league.
Then: pick factors on the older 70% of games only, fit, and test on the newest 30%.
"""
import math
import random
from collections import defaultdict, deque

from . import features as F


def logit(p):
    p = min(max(p, 0.01), 0.99)
    return math.log(p / (1 - p))


def sig(z):
    return 1 / (1 + math.exp(-max(-30, min(30, z))))


def derive(rows, league):
    """Home-minus-away differences, matchup terms, market terms, and market-residual momentum."""
    resid = defaultdict(lambda: deque(maxlen=10))  # team -> recent (won - kalshi price)
    out = []
    for r in rows:
        x = {}
        for k in list(r):
            if k.startswith("h_") and ("a_" + k[2:]) in r and isinstance(r[k], (int, float)) and isinstance(r["a_" + k[2:]], (int, float)):
                x["diff_" + k[2:]] = r[k] - r["a_" + k[2:]]
        g = lambda k: r.get(k) or 0.0  # noqa: E731
        if league == "nba":
            x["mu_off_vs_def"] = (g("h_off_rtg") - g("a_def_rtg")) - (g("a_off_rtg") - g("h_def_rtg"))
            x["mu_three_volume_vs_allowed"] = g("h_three_rate") * g("a_opp_three_rate") - g("a_three_rate") * g("h_opp_three_rate")
            x["mu_three_skill_vs_defense"] = (g("h_three_pct") - g("a_opp_three_pct")) - (g("a_three_pct") - g("h_opp_three_pct"))
            x["mu_rim_attack_vs_rim_d"] = g("h_rim_share") * g("a_opp_rim_fg") - g("a_rim_share") * g("h_opp_rim_fg")
            x["mu_paint"] = (g("h_paint_pts") - g("a_opp_paint_pts")) - (g("a_paint_pts") - g("h_opp_paint_pts"))
            x["mu_turnovers"] = (g("h_forced_tov_pct") - g("a_tov_pct")) - (g("a_forced_tov_pct") - g("h_tov_pct"))
            x["mu_free_throws"] = (g("h_ft_rate") - g("a_opp_ft_rate")) - (g("a_ft_rate") - g("h_opp_ft_rate"))
            x["abs_pace_gap"] = abs(g("h_pace") - g("a_pace"))
        else:
            x["mu_run_vs_run_d"] = g("h_run_rate") * g("a_def_rush_ypc") - g("a_run_rate") * g("h_def_rush_ypc")
            x["mu_pass_vs_pass_d"] = (1 - g("h_run_rate")) * (g("h_pass_ypa") - g("a_def_pass_ypa")) - (1 - g("a_run_rate")) * (g("a_pass_ypa") - g("h_def_pass_ypa"))
            x["mu_ypp_vs_def"] = (g("h_ypp") - g("a_def_ypp")) - (g("a_ypp") - g("h_def_ypp"))
            x["mu_pass_rush"] = (g("a_sacks_taken") + g("h_sacks_made")) - (g("h_sacks_taken") + g("a_sacks_made"))
            x["mu_turnover_margin"] = (g("h_takeaways") - g("h_giveaways")) - (g("a_takeaways") - g("a_giveaways"))
            x["mu_third_down"] = (g("h_third_pct") - g("a_def_third_pct")) - (g("a_third_pct") - g("h_def_third_pct"))
            x["mu_red_zone"] = (g("h_rz_pct") - g("a_def_rz_pct")) - (g("a_rz_pct") - g("h_def_rz_pct"))
            if "temp_f" in r:
                x["env_cold_vs_dome_visitor"] = r["a_dome_team"] * (1 if r["temp_f"] < 40 else 0)
                x["env_wind"] = r["wind_mph"]
                x["env_temp"] = r["temp_f"]
                x["env_rain_snow"] = 1 if (r["precip_mm"] > 1 or r["snow_cm"] > 0) else 0
                x["env_wind_x_pass_gap"] = r["wind_mph"] * ((1 - g("h_run_rate")) - (1 - g("a_run_rate")))
            x["qb_change_diff"] = g("h_qb_change") - g("a_qb_change")
            x["west_team_early_east"] = 1 if (r.get("a_tz_from_home", 0) >= 2 and r.get("a_body_clock_hour", 12) <= 10) else 0
            x["short_week_diff"] = (1 if g("h_rest") <= 5 else 0) - (1 if g("a_rest") <= 5 else 0)
            x["bye_diff"] = (1 if g("h_rest") >= 12 else 0) - (1 if g("a_rest") >= 12 else 0)
        for k in ("national_tv", "primetime", "conference_game", "playoffs", "international", "venue_dome", "neutral",
                  "ref_home_bias", "ref_total_bias", "start_hour_et"):
            x["ctx_" + k] = r.get(k, 0) or 0
        x["ctx_weekend"] = 1 if r.get("day_of_week") in (5, 6) else 0
        x["ctx_season_phase"] = min(g("h_games"), 82) if league == "nba" else (r.get("week") or 0)
        x["elo_logit"] = logit(r["elo_home_prob"])
        if "kalshi_home_3h" in r:
            p = r["kalshi_home_3h"]
            x["mkt_move_open_to_3h"] = logit(p) - logit(r["kalshi_home_open"])
            x["mkt_late_move_3h_to_1h"] = logit(r["kalshi_home_1h"]) - logit(p)   # info that arrives AFTER our price
            x["mkt_spread"] = r["kalshi_spread_3h"]
            x["mkt_log_open_interest"] = math.log1p(r["kalshi_oi_3h"])
            x["mkt_favorite_strength"] = abs(logit(p))
            x["elo_vs_market"] = x["elo_logit"] - logit(p)
            sb = F.sportsbook_home_prob(r, league)
            if sb:
                x["sportsbook_vs_kalshi"] = logit(sb) - logit(p)
            x["mkt_resid_momentum"] = (sum(resid[r["home"]]) / max(1, len(resid[r["home"]]))) - (sum(resid[r["away"]]) / max(1, len(resid[r["away"]])))
            if r.get("home_win") is not None:
                resid[r["home"]].append(r["home_win"] - p)
                resid[r["away"]].append((1 - r["home_win"]) - (1 - p))
        out.append({"row": r, "x": x})
    return out


def fit_offset(xs, ys, offs, lam=1.0, iters=40):
    """logistic: y ~ offset + a + b*x  (offset = 0 for the raw test). Returns a, b, se(b)."""
    a = b = 0.0
    for _ in range(iters):
        ga = gb = 0.0
        haa = hab = hbb = lam
        for x, y, o in zip(xs, ys, offs):
            p = sig(o + a + b * x)
            w = p * (1 - p)
            ga += p - y
            gb += (p - y) * x
            haa += w
            hab += w * x
            hbb += w * x * x
        gb += lam * b
        ga += lam * a
        det = haa * hbb - hab * hab
        if det <= 0:
            break
        da = (hbb * ga - hab * gb) / det
        db = (haa * gb - hab * ga) / det
        a -= da
        b -= db
        if abs(da) + abs(db) < 1e-9:
            break
    det = haa * hbb - hab * hab
    se = math.sqrt(haa / det) if det > 0 else float("inf")
    return a, b, se


def bh(pvals):
    order = sorted(range(len(pvals)), key=lambda i: pvals[i])
    q = [1.0] * len(pvals)
    prev = 1.0
    for rank, i in reversed(list(enumerate(order, 1))):
        prev = min(prev, pvals[i] * len(pvals) / rank)
        q[i] = prev
    return q


def pval(z):
    return math.erfc(abs(z) / math.sqrt(2))


def test_all(data, min_n=150):
    """data: list of {'x': {...}, 'y': 0/1, 'p': market prob}. Returns per-factor results."""
    names = sorted({k for d in data for k in d["x"]})
    res = []
    for k in names:
        rows = [d for d in data if k in d["x"] and d["x"][k] is not None]
        if len(rows) < min_n:
            continue
        vals = [d["x"][k] for d in rows]
        mu = sum(vals) / len(vals)
        sd = math.sqrt(sum((v - mu) ** 2 for v in vals) / len(vals)) or 1.0
        xs = [(v - mu) / sd for v in vals]
        ys = [d["y"] for d in rows]
        _, b_raw, se_raw = fit_offset(xs, ys, [0.0] * len(xs))
        _, b_mkt, se_mkt = fit_offset(xs, ys, [logit(d["p"]) for d in rows])
        res.append({"factor": k, "n": len(rows), "raw_b": b_raw, "raw_z": b_raw / se_raw,
                    "mkt_b": b_mkt, "mkt_z": b_mkt / se_mkt})
    for kind in ("raw", "mkt"):
        qs = bh([pval(r[f"{kind}_z"]) for r in res])
        for r, q in zip(res, qs):
            r[f"{kind}_q"] = q
    return res


def walk_forward(data, factors, train_frac=0.7, lam=5.0):
    """Multi-factor model on top of the market, fitted on the older part, scored on the newer part."""
    data = [d for d in data if all(f in d["x"] and d["x"][f] is not None for f in factors)]
    if len(data) < 100 or not factors:
        return None
    k = int(len(data) * train_frac)
    tr, te = data[:k], data[k:]
    stats = {}
    for f in factors:
        v = [d["x"][f] for d in tr]
        mu = sum(v) / len(v)
        sd = math.sqrt(sum((a - mu) ** 2 for a in v) / len(v)) or 1.0
        stats[f] = (mu, sd)
    def X(d):
        return [1.0] + [(d["x"][f] - stats[f][0]) / stats[f][1] for f in factors]
    w = [0.0] * (len(factors) + 1)
    for _ in range(40):  # Newton with ridge
        n = len(w)
        g = [lam * w[i] if i else 0.0 for i in range(n)]
        H = [[(lam if i == j and i else 0.0) for j in range(n)] for i in range(n)]
        for d in tr:
            x = X(d)
            p = sig(logit(d["p"]) + sum(a * b for a, b in zip(w, x)))
            for i in range(n):
                g[i] += (p - d["y"]) * x[i]
                for j in range(n):
                    H[i][j] += p * (1 - p) * x[i] * x[j]
        M = [H[i][:] + [g[i]] for i in range(n)]
        for c in range(n):
            piv = max(range(c, n), key=lambda r_: abs(M[r_][c]))
            M[c], M[piv] = M[piv], M[c]
            if abs(M[c][c]) < 1e-12:
                continue
            for r_ in range(n):
                if r_ != c:
                    f_ = M[r_][c] / M[c][c]
                    for j in range(c, n + 1):
                        M[r_][j] -= f_ * M[c][j]
        step = [M[i][n] / M[i][i] if abs(M[i][i]) > 1e-12 else 0 for i in range(n)]
        w = [w[i] - step[i] for i in range(n)]
        if max(abs(s) for s in step) < 1e-8:
            break
    def ll(p, y):
        p = min(max(p, 1e-6), 1 - 1e-6)
        return -(y * math.log(p) + (1 - y) * math.log(1 - p))
    base = [ll(d["p"], d["y"]) for d in te]
    mod = [ll(sig(logit(d["p"]) + sum(a * b for a, b in zip(w, X(d)))), d["y"]) for d in te]
    diff = [b - m for b, m in zip(base, mod)]
    mean = sum(diff) / len(diff)
    sd = math.sqrt(sum((v - mean) ** 2 for v in diff) / (len(diff) - 1)) or 1e-9
    # what it does to picks: take the model's favourite in each test game
    fav_mkt = sum((d["p"] >= .5) == (d["y"] == 1) for d in te) / len(te)
    fav_mod = sum((sig(logit(d["p"]) + sum(a * b for a, b in zip(w, X(d)))) >= .5) == (d["y"] == 1) for d in te) / len(te)
    return {"n_train": len(tr), "n_test": len(te), "factors": factors, "weights": dict(zip(["intercept"] + factors, w)),
            "test_ll_market": sum(base) / len(base), "test_ll_model": sum(mod) / len(mod), "gain": mean,
            "z": mean / (sd / math.sqrt(len(diff))), "fav_hit_market": fav_mkt, "fav_hit_model": fav_mod}


def run(league, log=print):
    rows = F.attach_market(F.build(league), league)
    rows = [r for r in rows if r.get("home_win") is not None and not r.get("preseason")]
    D = derive(rows, league)
    data = [{"x": d["x"], "y": d["row"]["home_win"], "p": d["row"]["kalshi_home_3h"], "date": d["row"]["date"]}
            for d in D if "kalshi_home_3h" in d["row"]]
    data.sort(key=lambda d: d["date"])
    log(f"{league.upper()}: {len(rows)} games with ESPN data, {len(data)} with a Kalshi price 3h before")
    res = test_all(data)
    # choose factors using ONLY the training period, then test forward
    k = int(len(data) * 0.7)
    train_res = test_all(data[:k])
    chosen = [r["factor"] for r in sorted(train_res, key=lambda r: -abs(r["mkt_z"]))
              if abs(r["mkt_z"]) >= 2.5 and not r["factor"].startswith("mkt_late")][:8]
    wf = walk_forward(data, chosen)
    return {"league": league, "n_games": len(rows), "n_priced": len(data), "results": res, "chosen": chosen, "walk_forward": wf}
