# Kalshi Picks Bot (v2)

A rebuild of the old home-PC PowerShell bot. It runs on GitHub Actions every morning, scans **every
open Kalshi sports market** (game lines, spreads, totals, player props, quarters, tennis, esports, golf, ...),
emails two lists, grades itself against Kalshi's own settlement results, and retrains itself.

## What went wrong with the old bot

I recovered every pick from the 28 emails it sent (Jul 10 - Aug 4, 2026), removed repeats (243 unique picks),
and graded 241 of them against final scores. Raw data: `old_bot/old_picks_graded.csv`, scripts in `old_bot/`.

| | Record | Model said | Kalshi price said |
|---|---|---|---|
| **All picks** | 117-124 (48.5%) | 61.0% | 47.8% |
| MLB moneyline | 68-53 (56.2%) | 60.8% | 50.3% |
| MLB totals | 23-21 | 77.9% | 63.8% |
| -- MLB **Overs** | **2-10** | 66.4% | 54.9% |
| **MLS soccer** | **6-24 (20%)** | 57.8% | 36.8% |
| WNBA spreads | 4-14 | 29.4% | 16.4% |

Buying one contract on every pick would have made about **+$1.81 on 241 contracts before Kalshi fees,
which is roughly break-even, or a small loss after fees.**

The patterns:

1. **The model was badly overconfident.** It averaged a 61% win chance; picks actually won 48.5%,
   almost exactly what Kalshi's price implied (47.8%). The market was the better forecaster.
2. **The bigger the "edge", the worse the pick.** Edges of 20%+ went **7-23**. Edges under 8% went 21-14.
   A huge gap from the market almost always meant the model was wrong, not the market.
3. **Soccer ignored draws.** The win model was two-way, but a soccer "team wins" contract loses on a draw.
   That made every MLS road team look like a bargain (6-24).
4. **The World Cup model was a placeholder.** Every match came out 45.2% / 54.8% regardless of the teams.
5. **It recommended games that had already started.** It listed the Lynx/Liberty game at a "1% Kalshi price"
   (a +35% "edge") because the game was already in progress.
6. **Overs were miscalibrated** (2-10), probably because of the fixed, untuned scoring standard deviations.
7. One bright spot: **MLB favorites went 48-21 (+26% ROI)**. That's only 69 picks, so it could still be luck.

## How v2 is different

- **It starts from the Kalshi price, not against it.** For each market,
  `P = learned_correction(Kalshi price, team ratings)`. With no proof that it can do better,
  P is just the market price.
- **It learns from every market, not just its own picks.** Each run logs every liquid market's price.
  When markets settle, Kalshi's own result grades them, for any bet type in any sport.
  It also backfills thousands of already-settled markets with their pre-game prices.
- **Weights are learned per market family:** all markets → sport → series (e.g. `KXNBAGAME`).
  A family only gets its own weights if they beat its parent's on the **newest 25% of history, held out
  from training**. That stops the bot from fooling itself the way the old one did.
- **Team ratings (Elo)** from ESPN results for NFL, NBA, NHL, MLB, WNBA, college football and college
  basketball are a second opinion on game winners. The learner decides, per league, how much to trust them.
  Zero weight is a valid answer.
- **Safety filters:** skips games that have started (ESPN status and a time buffer), wide spreads, illiquid markets,
  and 97c+ "locks". Profit numbers include Kalshi's fee.

## What it has learned so far (first backfill, Nov 10 2026)

The learner was seeded with **17,231 settled sports markets** from the previous 21 days, each with its price
6 hours before the event, across 315 market types. Results on the newest 25%, held out from training:

- **Across all markets, it found no edge over Kalshi's price.** The log-loss was 0.5275 for the model and 0.5275 for the market.
  For most bet types, the price is already the best estimate, so v2 trusts it.
- **Game winners with team ratings, pooled across leagues (1,225 games), passed the significance test.**
  It now has its own learned family (`pool:game-winners-with-ratings`). Two effects:
  1. Favorites are underpriced. Game favorites priced 80-90c won 95% of the time.
  2. When the ESPN-based ratings rate the favorite *lower* than Kalshi does, the favorite still won more than its
     price said (80.8% against 75.4%, z=3.2). The market knows things box scores don't (injuries, lineups), and
     it still under-reacts. So the learned ratings weight is negative: lean *further* toward Kalshi.
  **NBA and NHL game winners** pass the test on their own with these weights, so they're eligible for "Best value".
  This is from three weeks of early-season games; the weekly re-learn will revise it.
- Rating-vs-market gaps are capped at about the 90th percentile seen in training, so a bad team match can't swing a pick.
- Several other families (NBA and college basketball games, NFL totals) *looked* better on the first pass, but didn't clear the
  2.5-standard-error bar, so they aren't trusted yet. More data from the daily runs will settle it either way.

A lesson from building it: the first backfill picked the highest-*volume* settled markets. That leaked results,
because props that hit trade heavily as they cash. Priced-at-30% NHL assist props then appeared to hit 74% of the time.
The backfill now samples at random and filters only on pre-game liquidity.

## The email

1. **Most likely to hit:** the highest win probability, one per game, priced at 92c or less. It shows the profit
   per $1 after fees. A negative number means "likely to win, but overpriced".
2. **Safest combos:** 2- and 3-leg combinations from that list, with the chance that every leg wins.
3. **Best value:** only from market families where the model has *proven* it beats the plain Kalshi price.
   Expect this list to be empty or short at first. That's deliberate.
4. **Track record**, graded automatically, and **what the bot has learned so far**.

## Setup (one time)

1. Turn on 2-Step Verification for the Gmail account, then create an **App Password**
   (Google Account → Security → App passwords).
2. In the GitHub repo: **Settings → Secrets and variables → Actions → New repository secret**:
   - `GMAIL_ADDRESS`: the Gmail address that sends the email
   - `GMAIL_APP_PASSWORD`: the 16-character app password
   - `PICKS_TO` (optional): where to send picks; defaults to `GMAIL_ADDRESS`
3. GitHub only runs scheduled workflows from the repo's **default branch**, so merge this branch into it.
4. Optional: **Actions → Kalshi picks → Run workflow** to run it right away. Set `backfill_days` to e.g. `30`
   to give the learner more history.

Run locally (Python 3.10+, no packages needed):

```bash
python -m kalshi_bot daily --no-email
```

```bash
python -m kalshi_bot backfill --days 21
```

```bash
python -m unittest discover -s kalshi_bot/tests -t .
```

Settings (time window, list sizes, price caps, learning thresholds) are in `config.py`.
Learned weights are in `data/weights.json`.

*Statistical estimates, not guarantees. Never bet money you can't afford to lose.*
