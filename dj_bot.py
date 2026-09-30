#!/usr/bin/env python3
"""DJ Mix Bot - picks the next song to mix.

It scores every track in your library against the song that is playing now,
using the three rules DJs rely on:

  1. BPM (tempo)   - songs within 3-5 BPM mix cleanly; the bot also tells you
                     how far to move your pitch slider to match exactly.
  2. Key (harmony) - uses the Camelot Wheel: same key, one step up/down, or the
                     relative major/minor all blend without clashing.
  3. Energy (vibe) - the next song should stay at the same energy level or move
                     up/down by only one level. Matching genre/mood is a bonus.

Run `python3 dj_bot.py --help` for usage. Only the Python standard library is
needed.
"""

import argparse
import csv
import re
import sys
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Camelot Wheel
# ---------------------------------------------------------------------------

# Musical key name -> Camelot code. "A" = minor keys, "B" = major keys.
MINOR_KEYS = {
    "G#": 1, "AB": 1, "D#": 2, "EB": 2, "A#": 3, "BB": 3, "F": 4, "C": 5,
    "G": 6, "D": 7, "A": 8, "E": 9, "B": 10, "F#": 11, "GB": 11, "C#": 12,
    "DB": 12,
}
MAJOR_KEYS = {
    "B": 1, "CB": 1, "F#": 2, "GB": 2, "DB": 3, "C#": 3, "AB": 4, "G#": 4,
    "EB": 5, "D#": 5, "BB": 6, "A#": 6, "F": 7, "C": 8, "G": 9, "D": 10,
    "A": 11, "E": 12,
}
# Friendly names for printing each Camelot code.
CAMELOT_NAMES = {
    "1A": "Ab minor", "2A": "Eb minor", "3A": "Bb minor", "4A": "F minor",
    "5A": "C minor", "6A": "G minor", "7A": "D minor", "8A": "A minor",
    "9A": "E minor", "10A": "B minor", "11A": "F# minor", "12A": "Db minor",
    "1B": "B major", "2B": "F# major", "3B": "Db major", "4B": "Ab major",
    "5B": "Eb major", "6B": "Bb major", "7B": "F major", "8B": "C major",
    "9B": "G major", "10B": "D major", "11B": "A major", "12B": "E major",
}


def to_camelot(key):
    """Convert a key like '8A', 'Am', 'A minor', 'C#', 'Dbmaj' to Camelot.

    Raises ValueError if the key can't be understood.
    """
    text = key.strip().upper().replace(" ", "").replace("♯", "#").replace("♭", "B")
    m = re.fullmatch(r"(1[0-2]|[1-9])([AB])", text)
    if m:
        return m.group(1) + m.group(2)
    m = re.fullmatch(r"([A-G][#B]?)(MINOR|MIN|M|MAJOR|MAJ)?", text)
    # A trailing lowercase "m" means minor; check the original casing for it.
    if m:
        note, quality = m.group(1), m.group(2) or "MAJ"
        is_minor = quality in ("MINOR", "MIN") or (
            quality == "M" and key.strip().replace(" ", "").endswith("m"))
        table = MINOR_KEYS if is_minor else MAJOR_KEYS
        if note in table:
            return f"{table[note]}{'A' if is_minor else 'B'}"
    raise ValueError(f"Unknown musical key: {key!r}")


def split_camelot(code):
    return int(code[:-1]), code[-1]


def wheel_distance(a, b):
    """Steps between two numbers on the 12-position wheel (0-6)."""
    d = abs(a - b) % 12
    return min(d, 12 - d)


def key_match(a, b):
    """Rate how well Camelot key `b` follows key `a`. Returns (score, label)."""
    num_a, let_a = split_camelot(a)
    num_b, let_b = split_camelot(b)
    steps = wheel_distance(num_a, num_b)
    if a == b:
        return 1.0, "same key - perfect"
    if let_a == let_b and steps == 1:
        return 0.9, "1 step on wheel - smooth"
    if num_a == num_b:
        return 0.85, "relative major/minor - mood change"
    if let_a != let_b and steps == 1:
        return 0.5, "diagonal move - use with care"
    if let_a == let_b and steps == 2:
        return 0.4, "2 steps - energy boost, risky"
    return 0.0, "keys clash"


# ---------------------------------------------------------------------------
# Tracks and library
# ---------------------------------------------------------------------------

@dataclass
class Track:
    title: str
    artist: str
    bpm: float
    key: str            # Camelot code, e.g. "8A"
    energy: int         # 1 (chill) .. 10 (peak)
    genre: str = ""
    mood: str = ""
    notes: str = ""     # cue points: where vocals start, the drop, the outro...

    def label(self):
        return f"{self.artist} - {self.title}"

    def summary(self):
        return (f"{self.label()}  [{self.bpm:g} BPM | {self.key} "
                f"({CAMELOT_NAMES[self.key]}) | energy {self.energy}"
                + (f" | {self.genre}" if self.genre else "") + "]")


def load_library(path):
    """Read tracks from a CSV with columns:
    title, artist, bpm, key, energy, genre, mood, notes
    (genre, mood and notes are optional).
    """
    tracks = []
    with open(path, newline="", encoding="utf-8") as f:
        for line_no, row in enumerate(csv.DictReader(f), start=2):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            try:
                energy = int(row["energy"])
                if not 1 <= energy <= 10:
                    raise ValueError("energy must be 1-10")
                tracks.append(Track(
                    title=row["title"],
                    artist=row.get("artist", ""),
                    bpm=float(row["bpm"]),
                    key=to_camelot(row["key"]),
                    energy=energy,
                    genre=row.get("genre", ""),
                    mood=row.get("mood", ""),
                    notes=row.get("notes", ""),
                ))
            except (KeyError, ValueError) as e:
                print(f"Skipping line {line_no} of {path}: {e}", file=sys.stderr)
    return tracks


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def bpm_match(current_bpm, next_bpm):
    """Compare tempos, allowing half/double time (e.g. 70 BPM vs 140 BPM).

    Returns (score, effective_bpm_difference, pitch_percent, note), where
    pitch_percent is how much to change the NEXT track's tempo slider so it
    matches the current track.
    """
    best = None
    for factor, note in ((1, ""), (2, "double-time"), (0.5, "half-time")):
        effective = next_bpm * factor
        diff = abs(effective - current_bpm)
        if best is None or diff < best[0]:
            best = (diff, effective, note)
    diff, effective, note = best
    pitch = (current_bpm / effective - 1) * 100
    if diff <= 3:
        score = 1.0
    elif diff <= 5:
        score = 0.8
    elif diff <= 8:
        score = 0.4   # possible, but the pitch change becomes audible
    else:
        score = 0.0
    return score, diff, pitch, note


def energy_match(current, nxt, direction="steady"):
    """Score an energy change. `direction` is 'up', 'down' or 'steady'."""
    change = nxt - current
    if abs(change) > 2:
        return 0.0
    if abs(change) == 2:
        return 0.3
    if direction == "up":
        return {1: 1.0, 0: 0.8, -1: 0.4}[change]
    if direction == "down":
        return {-1: 1.0, 0: 0.8, 1: 0.4}[change]
    return {0: 1.0, 1: 0.85, -1: 0.85}[change]


WEIGHTS = {"bpm": 0.35, "key": 0.35, "energy": 0.2, "vibe": 0.1}


@dataclass
class Suggestion:
    track: Track
    score: float                 # 0-100
    reasons: list = field(default_factory=list)
    pitch: float = 0.0


def score_transition(current, nxt, direction="steady"):
    """Score how well `nxt` follows `current`. Returns a Suggestion, or None
    if any rule is broken badly enough that the mix would sound bad."""
    b_score, b_diff, pitch, tempo_note = bpm_match(current.bpm, nxt.bpm)
    k_score, k_label = key_match(current.key, nxt.key)
    e_score = energy_match(current.energy, nxt.energy, direction)
    if b_score == 0 or k_score == 0 or e_score == 0:
        return None

    same_genre = bool(current.genre) and current.genre.lower() == nxt.genre.lower()
    same_mood = bool(current.mood) and current.mood.lower() == nxt.mood.lower()
    vibe = 0.6 * same_genre + 0.4 * same_mood

    total = (WEIGHTS["bpm"] * b_score + WEIGHTS["key"] * k_score
             + WEIGHTS["energy"] * e_score + WEIGHTS["vibe"] * vibe)

    tempo = f"BPM off by {b_diff:.1f}"
    if tempo_note:
        tempo += f" ({tempo_note})"
    tempo += f" -> set pitch {pitch:+.1f}%"
    change = nxt.energy - current.energy
    energy = ("energy steady" if change == 0
              else f"energy {'up' if change > 0 else 'down'} {abs(change)}")
    reasons = [tempo, f"key {current.key} -> {nxt.key}: {k_label}", energy]
    if vibe:
        reasons.append("same " + " & ".join(
            w for w, ok in (("genre", same_genre), ("mood", same_mood)) if ok))
    return Suggestion(nxt, round(total * 100, 1), reasons, pitch)


def suggest_next(current, library, played=(), direction="steady", limit=5):
    """Return the best tracks to mix after `current`, best first."""
    skip = {id(t) for t in played} | {id(current)}
    results = []
    for track in library:
        if id(track) in skip:
            continue
        s = score_transition(current, track, direction)
        if s:
            results.append(s)
    results.sort(key=lambda s: s.score, reverse=True)
    return results[:limit]


def build_set(start, library, length=10, arc="build"):
    """Plan a whole set from `start`, one best next track at a time.

    arc: 'build'  - energy climbs through the set
         'steady' - energy stays level
         'wave'   - climb for the first two-thirds, then cool down
    """
    played = [start]
    while len(played) < length:
        pos = len(played) / length
        if arc == "build":
            direction = "up"
        elif arc == "wave":
            direction = "up" if pos < 2 / 3 else "down"
        else:
            direction = "steady"
        options = suggest_next(played[-1], library, played, direction, limit=1)
        if not options:
            break
        played.append(options[0].track)
    return played


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

def find_track(query, library):
    """Find a track by list number (1-based) or part of its title/artist."""
    query = query.strip()
    if query.isdigit() and 1 <= int(query) <= len(library):
        return library[int(query) - 1]
    matches = [t for t in library if query.lower() in t.label().lower()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise LookupError(f"No track matches {query!r}")
    names = "\n  ".join(t.label() for t in matches[:10])
    raise LookupError(f"{query!r} matches several tracks:\n  {names}")


def print_suggestions(current, suggestions):
    print(f"\nNow playing: {current.summary()}")
    if current.notes:
        print(f"  cue notes: {current.notes}")
    if not suggestions:
        print("\nNo good matches left. Try a different energy direction, or "
              "use a break/effect to reset the tempo.")
        return
    print("\nBest next tracks:")
    for i, s in enumerate(suggestions, 1):
        print(f"\n {i}. [{s.score:5.1f}] {s.track.summary()}")
        for r in s.reasons:
            print(f"      - {r}")
        if s.track.notes:
            print(f"      cue notes: {s.track.notes}")


def cmd_list(library, _args):
    for i, t in enumerate(library, 1):
        print(f"{i:3}. {t.summary()}")


def cmd_next(library, args):
    current = find_track(args.track, library)
    print_suggestions(current, suggest_next(
        current, library, direction=args.direction, limit=args.count))


def cmd_set(library, args):
    start = find_track(args.track, library)
    tracks = build_set(start, library, args.length, args.arc)
    print(f"\nSet plan ({args.arc}, {len(tracks)} tracks):\n")
    for i, t in enumerate(tracks, 1):
        line = f"{i:3}. {t.summary()}"
        if i > 1:
            s = score_transition(tracks[i - 2], t)
            pitch = bpm_match(tracks[i - 2].bpm, t.bpm)[2]
            line += f"\n       mix score {s.score if s else '-'} | pitch {pitch:+.1f}%"
        print(line)
    if len(tracks) < args.length:
        print("\n(Stopped early - no more tracks mix well. Add more songs "
              "to your library or try a different arc.)")


INTERACTIVE_HELP = """Commands:
  play <number|name>   mark a track as playing and get suggestions
  up / down / steady   change the energy direction you want
  list                 show the whole library
  history              show what you've played
  help                 show this help
  quit                 exit
After suggestions, type just the suggestion number (1-5) to play it next."""


def cmd_interactive(library, args):
    print("DJ Mix Bot - live mode. Type 'help' for commands.")
    played, direction, last = [], args.direction, []
    while True:
        try:
            line = input(f"\n[{direction}] > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        cmd, _, rest = line.partition(" ")
        cmd = cmd.lower()
        try:
            if cmd in ("quit", "exit", "q"):
                break
            elif cmd == "help":
                print(INTERACTIVE_HELP)
            elif cmd == "list":
                cmd_list(library, args)
            elif cmd in ("up", "down", "steady"):
                direction = cmd
                print(f"Energy direction set to {direction}.")
                if played:
                    last = suggest_next(played[-1], library, played, direction, args.count)
                    print_suggestions(played[-1], last)
            elif cmd == "history":
                for i, t in enumerate(played, 1):
                    print(f"{i:3}. {t.summary()}")
            else:
                if cmd.isdigit() and last and 1 <= int(cmd) <= len(last):
                    track = last[int(cmd) - 1].track
                elif cmd == "play":
                    track = find_track(rest, library)
                else:
                    print("Unknown command. Type 'help'.")
                    continue
                played.append(track)
                last = suggest_next(track, library, played, direction, args.count)
                print_suggestions(track, last)
        except LookupError as e:
            print(e)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="DJ Mix Bot: suggests which song to mix next by BPM, key and energy.")
    parser.add_argument("-l", "--library", default="sample_library.csv",
                        help="CSV file of your tracks (default: sample_library.csv)")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="show every track in the library")

    p = sub.add_parser("next", help="suggest what to play after a track")
    p.add_argument("track", help="track number from 'list' or part of its name")
    p.add_argument("-d", "--direction", choices=["up", "down", "steady"], default="steady",
                   help="which way you want the energy to go")
    p.add_argument("-n", "--count", type=int, default=5, help="how many suggestions")

    p = sub.add_parser("set", help="plan a whole set starting from a track")
    p.add_argument("track", help="track number from 'list' or part of its name")
    p.add_argument("--length", type=int, default=10, help="number of tracks")
    p.add_argument("--arc", choices=["build", "steady", "wave"], default="wave",
                   help="energy shape of the set")

    p = sub.add_parser("live", help="interactive mode while you DJ (default)")
    p.add_argument("-d", "--direction", choices=["up", "down", "steady"], default="steady")
    p.add_argument("-n", "--count", type=int, default=5)

    args = parser.parse_args(argv)
    try:
        library = load_library(args.library)
    except FileNotFoundError:
        parser.error(f"library file not found: {args.library}")
    if not library:
        parser.error(f"no valid tracks in {args.library}")

    if args.command is None:
        args = parser.parse_args(["-l", args.library, "live"])
    handlers = {"list": cmd_list, "next": cmd_next, "set": cmd_set,
                "live": cmd_interactive}
    try:
        handlers[args.command](library, args)
    except LookupError as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
