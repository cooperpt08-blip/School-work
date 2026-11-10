"""Research-backed adjustments the live bot applies on top of the learned market weights.

1. Prop-line bias (research/props.py): Kalshi over-prices "normal night" overs (line near the
   player's usual production) and under-prices real long-shot overs. We measure where tonight's
   line sits against the player's recent-weighted average (in units of his game-to-game spread)
   and shift the price by the coefficient fitted on ~9,000 settled props.
2. Same-game parlay correlations (research/run_props.py): how much more/less often two legs from
   the same game hit together than if independent.
"""
import json
import math
from collections import defaultdict

from . import config
from .model import logit, sigmoid

# measured on settled Kalshi props, both legs as YES / "over" (both-hit rate / independent rate)
PAIR_LIFT = {
    ("nba", "same_player"): 1.25,       # same player, two stats (e.g. points + rebounds)   z=+4.5
    ("nba", "player_team_win"): 1.13,   # player over + his team wins                       z=+1.8
    ("nba", "player_opp_win"): 0.85,    # player over + the OTHER team wins                 z=-2.9  (avoid)
    ("nba", "teammates"): 0.95,         # two teammates both over (they share the ball)     z=-3.1  (avoid)
    ("nba", "opponents"): 1.05,
    ("nfl", "same_player"): 0.72,       # e.g. a back's rushing + receiving yards           z=-3.1  (avoid)
    ("nfl", "teammates"): 1.0,
    ("nfl", "opponents"): 1.0,
}
PROP_SERIES = {"KXNBAPTS": "nba", "KXNBAREB": "nba", "KXNBAAST": "nba", "KXNBA3PT": "nba",
               "KXNFLRECYDS": "nfl", "KXNFLRSHYDS": "nfl", "KXNFLPASSYDS": "nfl"}
GAME_SERIES = {"KXNBAGAME": "nba", "KXNFLGAME": "nfl"}


class PropSignals:
    def __init__(self, log=print):
        self.ok = False
        f = config.DATA / "research_weights.json"
        if not f.exists():
            return
        self.w = json.loads(f.read_text())["leagues"]
        try:
            from .research import features as F
            from .research import props as P
        except ImportError:
            return
        self.P = P
        self.hist = defaultdict(list)  # (series, normalized name) -> recent stat values
        for league in ("nba", "nfl"):
            if not (F.DATA / f"{league}_games.jsonl.gz").exists():
                continue
            series = [s for s, lg in PROP_SERIES.items() if lg == league]
            for g in F.load_games(league):
                if g.get("season_type") == 1:
                    continue
                for s in series:
                    for d in P.player_lines(league, g, s).values():
                        if d.get("dnp") or (league == "nba" and d["minutes"] <= 0):
                            continue
                        h = self.hist[(s, P.norm_name(d["name"]))]
                        h.append(d["stat"])
                        if len(h) > 60:
                            del h[:-60]
        self.ok = bool(self.hist)
        log(f"  research signals: player histories for {len(self.hist)} player-stats")

    def adjust(self, series, market, p_yes):
        """-> (adjusted P(yes), proven?) or None if not a covered prop."""
        lg = PROP_SERIES.get(series)
        if not self.ok or not lg or lg not in self.w or market.get("floor_strike") is None:
            return None
        name = (market.get("title") or "").split(":")[0]
        vals = self.hist.get((series, self.P.norm_name(name)))
        if not vals or len(vals) < 5:
            return None
        w = [0.5 ** (i / 8) for i in range(len(vals))][::-1]
        mean = sum(a * b for a, b in zip(vals, w)) / sum(w)
        sd = math.sqrt(sum(b * (a - mean) ** 2 for a, b in zip(vals, w)) / sum(w)) or 1.0
        cushion = (mean - float(market["floor_strike"])) / max(sd, 1.0)
        c = self.w[lg]
        # Only inside what the research actually covered: it studied the middle rung of each prop
        # ladder (priced ~7-50%). Low rungs priced 80-90% were never tested - don't extrapolate to them.
        if not (c.get("p_lo", 0.05) <= p_yes <= c.get("p_hi", 0.55)):
            return None
        z = min(max((cushion - c["mu"]) / c["sd"], c.get("z_lo", -2)), c.get("z_hi", 2))
        return sigmoid(logit(p_yes) + c["a"] + c["b"] * z), bool(c.get("proven"))


def player_code(ticker):
    parts = ticker.split("-")
    return parts[2] if len(parts) >= 4 else None


def pair_lift(a, b):
    """Correlation multiplier for two legs (only legs we have measured; otherwise 1.0)."""
    if a["game"] != b["game"]:
        return 1.0
    la, lb = PROP_SERIES.get(a["series"]) or GAME_SERIES.get(a["series"]), PROP_SERIES.get(b["series"]) or GAME_SERIES.get(b["series"])
    if not la or la != lb:
        return 1.0
    pa, pb = a["series"] in PROP_SERIES, b["series"] in PROP_SERIES
    if pa and pb and a["side"] == "yes" and b["side"] == "yes":
        ca, cb = player_code(a["ticker"]), player_code(b["ticker"])
        if ca and ca == cb:
            return PAIR_LIFT.get((la, "same_player"), 1.0)
        same_team = ca and cb and _team_of(a) == _team_of(b)
        return PAIR_LIFT.get((la, "teammates" if same_team else "opponents"), 1.0)
    if pa != pb:  # one prop over + one game-winner leg
        prop, game = (a, b) if pa else (b, a)
        if prop["side"] != "yes" or game["side"] != "yes":
            return 1.0
        winner = game["ticker"].rsplit("-", 1)[-1]
        return PAIR_LIFT.get((la, "player_team_win" if _team_of(prop) == winner else "player_opp_win"), 1.0)
    return 1.0


def _team_of(prop):
    code = player_code(prop["ticker"]) or ""
    teams = prop["game"][7:]  # e.g. NOPGSW
    for n in (4, 3, 2):
        if code[:n] and (teams.startswith(code[:n]) or teams.endswith(code[:n])):
            return code[:n]
    return code[:3]
