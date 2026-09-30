# DJ Mix Bot

A command-line bot that tells you **which song to mix next**. It checks every
track in your library against the song that's playing and ranks them by the
three rules DJs use:

| Rule | What the bot checks |
|------|---------------------|
| **BPM (tempo)** | Tracks within 3 BPM score best and 3–5 BPM is still good. Up to 8 BPM is allowed but scored low; anything further is rejected. Half/double time counts too (62 BPM mixes with 124). For every suggestion it tells you how far to move the **pitch slider** (e.g. `set pitch -1.6%`). |
| **Key (harmonic mixing)** | Keys are put on the **Camelot Wheel** (`8A`, `9B`, …). Same key = perfect, ±1 number = smooth, same number A↔B = relative major/minor. Diagonal and ±2 moves are allowed but scored low. Clashing keys are rejected. |
| **Energy & vibe** | Energy is 1–10. The next track should stay level or move by one. You can pick a direction: `up`, `down` or `steady`. Tracks with the same genre or mood get a bonus. |

Each suggestion also shows your **cue notes** for that track: where the vocals
start, where the drop is, and where the outro begins.

## Requirements

Python 3.8+ (standard library only, nothing to install).

## Your music library

Put your tracks in a CSV file (see `sample_library.csv`; its tracks are made-up examples):

```csv
title,artist,bpm,key,energy,genre,mood,notes
Sunrise Groove,DJ Example,120,8A,4,house,chill,Vocals at 0:32; outro starts 5:10
```

- `key` can be Camelot (`8A`) or a normal key name (`Am`, `A minor`, `C#m`, `Bb`, `Cmaj`).
- `energy` is 1 (chill) to 10 (peak time).
- `genre`, `mood` and `notes` are optional.

Most DJ software (Rekordbox, Serato, Traktor, Mixed In Key) can detect BPM and key for you.

## Usage

```bash
# Live mode (default): tell it what's playing and get suggestions as you go
python3 dj_bot.py
python3 dj_bot.py -l my_tracks.csv

# Show the library
python3 dj_bot.py list

# What should I play after this? (by list number or part of the name)
python3 dj_bot.py next "Lost Signals"
python3 dj_bot.py next 4 --direction up --count 3

# Plan a whole set. Arcs: build (energy climbs), steady, wave (climb, then cool down)
python3 dj_bot.py set "Warm Up" --length 12 --arc wave
```

### Live mode commands

```
play <number|name>   mark a track as playing and get suggestions
1-5                  play that suggestion next
up / down / steady   change the energy direction
list / history       show the library / what you've played
quit
```

Tracks you've already played are never suggested again.

### Example

```
Now playing: Test Pattern - Lost Signals  [124 BPM | 9A (E minor) | energy 6 | tech house]
  cue notes: Drop at 1:20; vocal loop 2:40

Best next tracks:

 1. [ 93.5] Rhythm Section - Pulse  [126 BPM | 10A (B minor) | energy 7 | tech house]
      - BPM off by 2.0 -> set pitch -1.6%
      - key 9A -> 10A: 1 step on wheel - smooth
      - energy up 1
      - same genre & mood
      cue notes: Big drop at 1:36
```

## How the score works

Score (0–100) = 35% BPM + 35% key + 20% energy + 10% genre/mood.
A track is left out completely if its tempo, key or energy is too far off.
You can change the weights in `WEIGHTS` in `dj_bot.py`.

## Tests

```bash
python3 -m unittest -v
```
