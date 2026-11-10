import unittest

from kalshi_bot import scan, signals


def leg(ticker, series, side="yes", prob=0.8, price=0.78):
    ev = ticker.split("-")[1]
    return {"ticker": ticker, "series": series, "side": side, "prob": prob, "price": price, "game": ev,
            "spread": 0.01, "proven": False, "ev": 0.0}


class ParlayTests(unittest.TestCase):
    def test_same_player_two_stats_is_boosted(self):
        a = leg("KXNBAPTS-26NOV09NOPGSW-NOPTMURPHY25-20", "KXNBAPTS")
        b = leg("KXNBAREB-26NOV09NOPGSW-NOPTMURPHY25-6", "KXNBAREB")
        self.assertAlmostEqual(signals.pair_lift(a, b), signals.PAIR_LIFT[("nba", "same_player")])

    def test_teammates_and_opponent_win_are_penalised(self):
        a = leg("KXNBAPTS-26NOV09NOPGSW-NOPTMURPHY25-20", "KXNBAPTS")
        b = leg("KXNBAPTS-26NOV09NOPGSW-NOPZWILLIAMSON1-25", "KXNBAPTS")
        self.assertLess(signals.pair_lift(a, b), 1.0)
        opp_win = leg("KXNBAGAME-26NOV09NOPGSW-GSW", "KXNBAGAME")
        own_win = leg("KXNBAGAME-26NOV09NOPGSW-NOP", "KXNBAGAME")
        self.assertLess(signals.pair_lift(a, opp_win), 1.0)
        self.assertGreater(signals.pair_lift(a, own_win), 1.0)

    def test_different_games_independent(self):
        a = leg("KXNBAPTS-26NOV09NOPGSW-NOPTMURPHY25-20", "KXNBAPTS")
        b = leg("KXNBAPTS-26NOV09BOSNYK-BOSJTATUM0-25", "KXNBAPTS")
        self.assertEqual(signals.pair_lift(a, b), 1.0)
        self.assertAlmostEqual(scan.joint([a, b]), 0.64)

    def test_best_parlay_prefers_helpful_same_game_legs(self):
        legs = [leg("KXNBAPTS-26NOV09NOPGSW-NOPTMURPHY25-20", "KXNBAPTS", prob=0.80),
                leg("KXNBAREB-26NOV09NOPGSW-NOPTMURPHY25-6", "KXNBAREB", prob=0.80),
                leg("KXNBAPTS-26NOV09BOSNYK-BOSJTATUM0-25", "KXNBAPTS", prob=0.81)]
        best2 = scan.best_parlays(legs)[0]
        self.assertEqual({x["series"] for x in best2["legs"]}, {"KXNBAPTS", "KXNBAREB"})
        self.assertGreater(best2["prob"], best2["independent_prob"])


if __name__ == "__main__":
    unittest.main()
