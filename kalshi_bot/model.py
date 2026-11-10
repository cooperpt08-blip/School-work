"""Probability model + self-learning.

For every market the bot starts from Kalshi's own price (the crowd is usually right) and then
applies *learned* corrections:

    logit(P) = a + b * logit(kalshi_mid) + c * (logit(elo) - logit(kalshi_mid))

  a, b  -> fix systematic mispricing for that market family (e.g. longshots overpriced)
  c     -> how much to trust the team-strength ratings over the market (0 = ignore them)

Weights are learned per family in a hierarchy: all markets -> sport (tag) -> series.
A family only gets its own weights if they beat its parent's on the newest, held-out 25% of
history; a family is "proven" (eligible for the Best Value list) only if its weights beat the
plain Kalshi price on that held-out data. Until then the bot just trusts the market.
"""
import json
import math
from datetime import datetime, timezone

from . import config
from .ratings import LEAGUES

MARKET = (0.0, 1.0, 0.0)
POOL = "pool:game-winners-with-ratings"
POOL_SERIES = set(LEAGUES)


def logit(p):
    p = min(max(p, 0.01), 0.99)
    return math.log(p / (1 - p))


def sigmoid(z):
    if z < -30:
        return 0.0
    if z > 30:
        return 1.0
    return 1 / (1 + math.exp(-z))


MAX_RATING_GAP = 1.5  # ~90th percentile of |ratings - market| (log-odds) seen in training; beyond it we'd be guessing


def features(mid, p_elo):
    x1 = logit(mid)
    x2 = (logit(p_elo) - x1) if p_elo is not None else 0.0
    return (1.0, x1, max(-MAX_RATING_GAP, min(MAX_RATING_GAP, x2)))


def predict(theta, x):
    return sigmoid(sum(t * v for t, v in zip(theta, x)))


def _solve3(H, g):
    # Gaussian elimination for a 3x3 system
    M = [row[:] + [g[i]] for i, row in enumerate(H)]
    for c in range(3):
        piv = max(range(c, 3), key=lambda r: abs(M[r][c]))
        M[c], M[piv] = M[piv], M[c]
        if abs(M[c][c]) < 1e-12:
            return [0.0, 0.0, 0.0]
        for r in range(3):
            if r != c:
                f = M[r][c] / M[c][c]
                for k in range(c, 4):
                    M[r][k] -= f * M[c][k]
    return [M[i][3] / M[i][i] for i in range(3)]


def fit(data, prior, strength=None):
    """L2-regularised logistic regression pulled toward `prior`. data = [(x, y)]."""
    lam = config.PRIOR_STRENGTH if strength is None else strength
    th = list(prior)
    for _ in range(30):
        g = [lam * (th[i] - prior[i]) for i in range(3)]
        H = [[lam if i == j else 0.0 for j in range(3)] for i in range(3)]
        for x, y in data:
            p = predict(th, x)
            w = p * (1 - p)
            for i in range(3):
                g[i] += (p - y) * x[i]
                for j in range(3):
                    H[i][j] += w * x[i] * x[j]
        step = _solve3(H, g)
        th = [th[i] - step[i] for i in range(3)]
        if max(abs(s) for s in step) < 1e-7:
            break
    return tuple(th)


def _losses(theta, data):
    out = []
    for x, y in data:
        p = min(max(predict(theta, x), 1e-6), 1 - 1e-6)
        out.append(-(y * math.log(p) + (1 - y) * math.log(1 - p)))
    return out


def logloss(theta, data):
    return sum(_losses(theta, data)) / len(data) if data else float("nan")


def beats(theta, baseline, test, z=2.5):
    """True if `theta` beats `baseline` on held-out `test` by a margin that isn't plausibly luck:
    mean per-prediction log-loss gain >= MIN_IMPROVEMENT and >= z standard errors above zero."""
    if len(test) < 60:
        return False
    d = [b - a for a, b in zip(_losses(theta, test), _losses(baseline, test))]
    n = len(d)
    mean = sum(d) / n
    sd = math.sqrt(sum((v - mean) ** 2 for v in d) / (n - 1)) or 1e-12
    return mean >= config.MIN_IMPROVEMENT and mean >= z * sd / math.sqrt(n)


def _split(rows):
    rows = sorted(rows, key=lambda r: r["t"])
    k = int(len(rows) * (1 - config.TEST_FRACTION))
    return [(r["x"], r["y"]) for r in rows[:k]], [(r["x"], r["y"]) for r in rows[k:]]


def learn(rows, log=print):
    """rows: dicts with t (timestamp), x (features), y (0/1), tag, series. Returns weights dict."""
    out = {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "n_rows": len(rows), "families": {}}

    def family(key, frows, parent_theta):
        n = len(frows)
        train, test = _split(frows)
        if n < config.MIN_TRAIN_ROWS or len(test) < 30:
            return None
        cand = fit(train, parent_theta)
        adopted = beats(cand, parent_theta, test)
        eff = cand if adopted else parent_theta
        theta = fit([(r["x"], r["y"]) for r in frows], parent_theta) if adopted else parent_theta
        ll_eff, ll_m = logloss(eff, test), logloss(MARKET, test)
        info = {"n": n, "n_test": len(test), "theta": [round(v, 4) for v in theta], "own_weights": adopted,
                "test_logloss": round(ll_eff, 5), "test_logloss_market": round(ll_m, 5),
                "proven": beats(eff, MARKET, test),
                "test_hit_rate_market_fav": round(sum((1 if (x[1] > 0) == (y == 1) else 0) for x, y in test) / len(test), 4)}
        out["families"][key] = info
        log(f"  {key:<34} n={n:<6} own={'Y' if adopted else '-'} proven={'Y' if info['proven'] else '-'} "
            f"test LL {ll_eff:.4f} vs market {ll_m:.4f}")
        return theta

    root = family("all", rows, MARKET) or MARKET
    # Game winners that have team ratings, pooled across leagues: no single league has enough
    # games to prove anything early in a season, but together they can.
    pool_theta = family(POOL, [r for r in rows if r["series"] in POOL_SERIES and r["x"][2] != 0.0], root) or root
    by_tag = {}
    for r in rows:
        by_tag.setdefault(r["tag"], []).append(r)
    for tag, trows in sorted(by_tag.items()):
        t_theta = family(f"tag:{tag}", trows, root) or root
        by_series = {}
        for r in trows:
            by_series.setdefault(r["series"], []).append(r)
        for s, srows in sorted(by_series.items()):
            family(f"series:{s}", srows, pool_theta if s in POOL_SERIES else t_theta)
    return out


class Weights:
    def __init__(self, path=None):
        path = path or config.WEIGHTS
        self.w = json.loads(path.read_text()) if path.exists() else {"families": {}}

    def lookup(self, series, tag, has_ratings=False):
        fam = self.w.get("families", {})
        pool = [POOL] if series in POOL_SERIES and has_ratings else []
        keys = [f"series:{series}"] + pool + [f"tag:{tag}", "all"]
        for key in keys:
            if key in fam:
                f = fam[key]
                return tuple(f["theta"]), bool(f["proven"]), key
        return MARKET, False, "market"

    def prob(self, series, tag, mid, p_elo):
        theta, proven, key = self.lookup(series, tag, has_ratings=p_elo is not None)
        return predict(theta, features(mid, p_elo)), proven, key
