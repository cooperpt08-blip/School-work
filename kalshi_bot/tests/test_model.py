import random
import unittest

from kalshi_bot import model, ratings
from kalshi_bot.scan import game_key


def synth(n, true_theta, seed=0, with_elo=True, tag="Basketball", series="KXNBAGAME"):
    rnd = random.Random(seed)
    rows = []
    for i in range(n):
        mid = rnd.uniform(0.08, 0.92)
        elo = min(max(mid + rnd.uniform(-0.2, 0.2), 0.02), 0.98) if with_elo else None
        x = model.features(mid, elo)
        y = 1 if rnd.random() < model.predict(true_theta, x) else 0
        rows.append({"t": f"2026-10-{1 + i * 30 // n:02d}T{i % 24:02d}:00:00", "x": x, "y": y, "tag": tag, "series": series})
    return rows


class ModelTests(unittest.TestCase):
    def test_fit_recovers_known_weights(self):
        rows = synth(6000, (0.3, 1.2, 0.5))
        th = model.fit([(r["x"], r["y"]) for r in rows], model.MARKET, strength=0.1)
        self.assertAlmostEqual(th[0], 0.3, delta=0.12)
        self.assertAlmostEqual(th[1], 1.2, delta=0.12)
        self.assertAlmostEqual(th[2], 0.5, delta=0.15)

    def test_efficient_market_is_not_overridden(self):
        # outcomes generated exactly at the Kalshi price: the learner must NOT claim an edge
        rows = synth(3000, model.MARKET, seed=3)
        w = model.learn(rows, log=lambda *_: None)
        for key, fam in w["families"].items():
            self.assertFalse(fam["proven"], key)

    def test_real_edge_gets_proven(self):
        # the ratings carry real signal the market ignores -> should be learned and proven
        rows = synth(10000, (0.0, 1.0, 0.9), seed=5)
        w = model.learn(rows, log=lambda *_: None)
        self.assertTrue(w["families"]["all"]["proven"])
        self.assertGreater(w["families"]["all"]["theta"][2], 0.4)

    def test_weights_fallback_is_market(self):
        wts = model.Weights.__new__(model.Weights)
        wts.w = {"families": {}}
        p, proven, key = wts.prob("KXFOO", "Other", 0.63, None)
        self.assertAlmostEqual(p, 0.63, places=6)
        self.assertFalse(proven)


class MatchTests(unittest.TestCase):
    def test_event_date_and_game_key(self):
        self.assertEqual(str(ratings.event_date("KXNBAGAME-26NOV09CLECHA")), "2026-11-09")
        self.assertEqual(game_key("KXNBASPREAD-26NOV09CLECHA"), game_key("KXNBAGAME-26NOV09CLECHA"))

    def test_team_match(self):
        g = {"home": "Charlotte Hornets", "home_loc": "Charlotte", "home_abbr": "CHA",
             "away": "Cleveland Cavaliers", "away_loc": "Cleveland", "away_abbr": "CLE"}
        self.assertEqual(ratings._team_match("Cleveland", g, "away"), 3)
        self.assertEqual(ratings._team_match("Cleveland", g, "home"), 0)
        g2 = {"home": "Ohio State Buckeyes", "home_loc": "Ohio State", "home_abbr": "OSU",
              "away": "", "away_loc": "", "away_abbr": ""}
        self.assertEqual(ratings._team_match("Ohio St.", g2, "home"), 3)
        g3 = {"home": "LA Clippers", "home_loc": "LA", "home_abbr": "LAC",
              "away": "Los Angeles Lakers", "away_loc": "Los Angeles", "away_abbr": "LAL"}
        self.assertEqual(ratings._team_match("Los Angeles C", g3, "home"), 3)
        self.assertEqual(ratings._team_match("Los Angeles C", g3, "away"), 0)
        self.assertEqual(ratings._team_match("Los Angeles L", g3, "away"), 3)


if __name__ == "__main__":
    unittest.main()
