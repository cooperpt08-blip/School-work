import unittest

import dj_bot
from dj_bot import Track


def t(title, bpm, key, energy, genre="house", mood="dark"):
    return Track(title, "Test", bpm, key, energy, genre, mood)


class TestKeys(unittest.TestCase):
    def test_to_camelot(self):
        cases = {"8A": "8A", "8a": "8A", "Am": "8A", "A minor": "8A", "C": "8B",
                 "Cmaj": "8B", "F#m": "11A", "Dbm": "12A", "C#m": "12A",
                 "Bbm": "3A", "Bb": "6B", "E": "12B", "B♭": "6B"}
        for given, want in cases.items():
            self.assertEqual(dj_bot.to_camelot(given), want, given)

    def test_bad_key(self):
        with self.assertRaises(ValueError):
            dj_bot.to_camelot("H#")
        with self.assertRaises(ValueError):
            dj_bot.to_camelot("13A")

    def test_key_match(self):
        self.assertEqual(dj_bot.key_match("8A", "8A")[0], 1.0)
        self.assertEqual(dj_bot.key_match("8A", "9A")[0], 0.9)
        self.assertEqual(dj_bot.key_match("12A", "1A")[0], 0.9)  # wheel wraps
        self.assertEqual(dj_bot.key_match("8A", "8B")[0], 0.85)
        self.assertEqual(dj_bot.key_match("8A", "3A")[0], 0.0)


class TestBpmAndEnergy(unittest.TestCase):
    def test_bpm(self):
        self.assertEqual(dj_bot.bpm_match(124, 126)[0], 1.0)
        self.assertEqual(dj_bot.bpm_match(124, 128)[0], 0.8)
        self.assertEqual(dj_bot.bpm_match(100, 128)[0], 0.0)

    def test_half_time(self):
        score, diff, _, note = dj_bot.bpm_match(124, 62)
        self.assertEqual((score, diff, note), (1.0, 0, "double-time"))

    def test_pitch_percent(self):
        pitch = dj_bot.bpm_match(125, 120)[2]
        self.assertAlmostEqual(pitch, 125 / 120 * 100 - 100)

    def test_energy(self):
        self.assertEqual(dj_bot.energy_match(5, 5), 1.0)
        self.assertEqual(dj_bot.energy_match(5, 8), 0.0)
        self.assertGreater(dj_bot.energy_match(5, 6, "up"), dj_bot.energy_match(5, 4, "up"))
        self.assertGreater(dj_bot.energy_match(5, 4, "down"), dj_bot.energy_match(5, 6, "down"))


class TestSuggestions(unittest.TestCase):
    def setUp(self):
        self.now = t("Now", 124, "8A", 5)
        self.perfect = t("Perfect", 124, "8A", 5)
        self.good = t("Good", 126, "9A", 6)
        self.clash = t("Clash", 124, "2B", 5)
        self.too_fast = t("Too fast", 140, "8A", 5)
        self.too_hot = t("Too hot", 124, "8A", 9)
        self.lib = [self.now, self.perfect, self.good, self.clash, self.too_fast, self.too_hot]

    def test_ranking_and_filtering(self):
        picks = [s.track for s in dj_bot.suggest_next(self.now, self.lib)]
        self.assertEqual(picks, [self.perfect, self.good])

    def test_skips_played(self):
        picks = [s.track for s in dj_bot.suggest_next(self.now, self.lib, [self.perfect])]
        self.assertEqual(picks, [self.good])

    def test_build_set_no_repeats(self):
        lib = dj_bot.load_library("sample_library.csv")
        tracks = dj_bot.build_set(lib[0], lib, length=8, arc="build")
        self.assertEqual(len(tracks), len({id(x) for x in tracks}))
        for a, b in zip(tracks, tracks[1:]):
            self.assertIsNotNone(dj_bot.score_transition(a, b))

    def test_find_track(self):
        self.assertIs(dj_bot.find_track("2", self.lib), self.perfect)
        self.assertIs(dj_bot.find_track("clash", self.lib), self.clash)
        with self.assertRaises(LookupError):
            dj_bot.find_track("nothing here", self.lib)


if __name__ == "__main__":
    unittest.main()
