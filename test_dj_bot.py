import os
import tempfile
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


REKORDBOX_XML = """<?xml version="1.0" encoding="UTF-8"?>
<DJ_PLAYLISTS Version="1.0.0">
  <PRODUCT Name="rekordbox" Version="7.0.0" Company="AlphaTheta"/>
  <COLLECTION Entries="4">
    <TRACK TrackID="11" Name="Song One" Artist="Artist A" Genre="House"
           AverageBpm="124.00" Tonality="Am" Rating="153" Comments="" Location="file://localhost/a.mp3"/>
    <TRACK TrackID="12" Name="Song Two" Artist="Artist B" Genre="House"
           AverageBpm="125.00" Tonality="9A" Rating="0" Comments="9A - Energy 7" Location="file://localhost/b.mp3"/>
    <TRACK TrackID="13" Name="Not Analyzed" Artist="Artist C"
           AverageBpm="0.00" Tonality="" Rating="0" Location="file://localhost/c.mp3"/>
    <TRACK TrackID="14" Name="Other List" Artist="Artist D"
           AverageBpm="128.00" Tonality="C" Rating="0" Location="file://localhost/d.mp3"/>
  </COLLECTION>
  <PLAYLISTS>
    <NODE Type="0" Name="ROOT" Count="2">
      <NODE Name="Made to DJ" Type="1" KeyType="0" Entries="3">
        <TRACK Key="11"/><TRACK Key="12"/><TRACK Key="13"/>
      </NODE>
      <NODE Name="Other" Type="1" KeyType="1" Entries="1">
        <TRACK Key="file://localhost/d.mp3"/>
      </NODE>
    </NODE>
  </PLAYLISTS>
</DJ_PLAYLISTS>
"""

REKORDBOX_TXT = ("#\tTrack Title\tArtist\tGenre\tBPM\tRating\tKey\tComments\n"
                 "1\tSong One\tArtist A\tHouse\t124.00\t***\tAm\t\n"
                 "2\tSong Two\tArtist B\tHouse\t125.00\t\t9A\tEnergy 7\n")


class TestRekordboxImport(unittest.TestCase):
    def write(self, name, data, encoding="utf-8"):
        path = os.path.join(self.dir.name, name)
        with open(path, "w", encoding=encoding) as f:
            f.write(data)
        return path

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def test_xml_playlist(self):
        path = self.write("rb.xml", REKORDBOX_XML)
        tracks = dj_bot.load_library(path, "made to dj")
        self.assertEqual([t.title for t in tracks], ["Song One", "Song Two"])  # unanalyzed skipped
        self.assertEqual(tracks[0].key, "8A")
        self.assertEqual(tracks[0].energy, 6)    # 3 stars
        self.assertEqual(tracks[1].energy, 7)    # from comment

    def test_xml_whole_collection_and_location_keys(self):
        path = self.write("rb.xml", REKORDBOX_XML)
        self.assertEqual(len(dj_bot.load_library(path)), 3)
        self.assertEqual([t.title for t in dj_bot.load_library(path, "Other")], ["Other List"])
        with self.assertRaises(ValueError):
            dj_bot.load_library(path, "Nope")

    def test_txt_utf16(self):
        path = self.write("rb.txt", REKORDBOX_TXT, encoding="utf-16")
        tracks = dj_bot.load_library(path)
        self.assertEqual([(t.title, t.key, t.energy) for t in tracks],
                         [("Song One", "8A", 6), ("Song Two", "9A", 7)])

    def test_unknown_energy_still_suggested(self):
        a = t("A", 124, "8A", None)
        b = t("B", 124, "8A", 9)
        s = dj_bot.score_transition(a, b)
        self.assertIsNotNone(s)
        self.assertIn("energy unknown - use your ears", s.reasons)


if __name__ == "__main__":
    unittest.main()
