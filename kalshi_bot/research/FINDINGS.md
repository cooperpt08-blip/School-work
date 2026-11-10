# NBA / NFL deep dive: what predicts outcomes, and what beats Kalshi's price

Data (Nov 2026): every NBA and NFL game since fall 2024 from ESPN (box scores, every player's
line, who didn't play, shot profiles, referees, TV, DraftKings lines), Kalshi price histories for
1,424 NBA and 281 NFL game-winner markets, ~1,700 spreads/totals, ~9,000 player props, and
Open-Meteo kickoff weather (partial, see below). Every factor uses only information from earlier
games. Each factor was tested two ways:

- **Raw:** does it predict the result?
- **Beyond the price:** does it predict the result *after* knowing Kalshi's price 3 hours before?
  Only this kind can make money.

Results are corrected for testing many factors at once (Benjamini-Hochberg q < 0.10). The strongest
were then checked forward: chosen on the older 70% of games, scored on the newest 30%.

## Proven beyond Kalshi's price

| Finding | Evidence |
|---|---|
| **Player props are mis-priced by where the line sits.** Lines near a player's usual production: the over is **overpriced** (NBA: hit 31.2%, priced 36.2%). Real long-shot lines: the over is **underpriced** (hit 21.5%, priced 18.3%). | NBA z=-9.4, held-out z=2.7 (n=6,518). NFL z=-3.8, held-out z=1.9 (n=2,413) |
| **NBA Overs (game totals) are slightly overpriced** overall (hit 47.9%, priced 50.0%), most of all when the Over is the "expected" side. | z=-3.1, q=0.02 (n=781) |
| **NBA same-game parlay legs are correlated.** One player's two stats (points + rebounds...) hit together 8.6% vs 7.3% implied. Two teammates' overs (6.3% vs 6.9%) and a player's over + his *opponent* winning (10.1% vs 12.7%) work against each other. | z=+4.5 / -3.1 / -2.9 |
| **NFL: one player's two stats work against each other** (rushing + receiving yards: 4.3% vs 6.8%). | z=-3.1 |

## Promising, not yet confirmed on held-out games

- **NBA: regulars who missed the team's previous game.** The market under-reacts: when the away team
  missed more, the home team won 64.3% vs 57.2% priced (z=-3.7, q=0.02). Held-out improvement was
  positive but not significant (z=1.2-1.4).
- **Travel / time zones crossed (NBA):** consistently negative for the travelling team in game winners
  and spreads (z about -2.2 to -2.8), not significant after correction.
- **NFL pass defense** (yards per pass allowed): z=-2.8 for game winners, q=0.40.
- **NFL props: defense vs position** (z=+2.2) and **wind** lowering passing/receiving yards (z=-2.2, only
  520 props with weather so far).
- **NBA props:** more rest -> slightly fewer overs than priced (z=-3.3); a player's personal home/away
  split works *against* the price (z=-2.5).

## Predict the result, but already in Kalshi's price (no extra value)

Team ratings / Elo, win %, scoring margin, offensive and defensive efficiency, last-5 form, streaks,
rim defense, paint scoring, turnovers, rebounding, three-point shooting, pace, shot profile
(rim / mid-range / three / pull-ups / drives), off-vs-def matchups, players missing tonight (game day),
line movement, NFL yards per play, run/pass mix, sacks, third down, red zone, turnover margin.

## No effect found

Rest days and back-to-backs (game level), altitude, referees' home/scoring tendencies, national TV /
primetime, day of week, conference games, season phase, playoffs, pace mismatch, hot hands (last 5 vs
season), blowout risk, game total line (props), opponent pace (props), NFL short weeks / byes /
early body-clock kickoffs.

## Gaps and next steps

- **NFL weather** covers only part of the history: Open-Meteo's free daily limit was hit. The
  collector now makes one request per stadium, so the next run fills it in.
- Older-season props are still downloading. Rerun `python -m kalshi_bot.research.run_props nba|nfl`
  for a bigger sample.
- Player speed / tracking data and historical injury-report snapshots aren't freely available.
  Absences are rebuilt from box scores.
- Sportsbook lines from ESPN are near-closing lines, so the "sportsbook vs Kalshi" test is only fair
  against Kalshi's late price. Live, the bot can read the current line at the same moment.

## What the bot now uses

`kalshi_bot/signals.py`: the prop-line correction (NBA proven, NFL adjusts but isn't value-eligible),
applied only within the price/cushion range the research covered, and the measured same-game pair
correlations inside the parlay builder (`scan.best_parlays`).
