"""Tunable settings. Everything the bot *learns* lives in data/weights.json instead."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SNAPSHOTS = DATA / "snapshots"      # monthly gzipped CSVs of every market price the bot has seen
GAMES = DATA / "games"              # ESPN results per league (feeds the Elo team ratings)
RESULTS = DATA / "results.csv"      # Kalshi settlement result per market ticker
WEIGHTS = DATA / "weights.json"     # learned calibration / blend weights
PICKS_LOG = DATA / "picks_log.csv"  # every pick the bot has emailed, graded once settled
REPORT_DIR = DATA / "reports"

# --- Kalshi trading costs -----------------------------------------------------------
# Taker fee per contract is roughly 0.07 * P * (1 - P) (rounded up to the cent per order).
FEE_RATE = 0.07

# --- Which markets count ------------------------------------------------------------
HORIZON_HOURS = 48          # only look at markets whose event happens within this window
PREGAME_BUFFER_HOURS = 4    # Kalshi's occurrence time is ~ the expected END of a game, so skip
                            # anything due within this many hours (it may already be live).
                            # The old bot recommended live games priced at 1c - this prevents that.
MAX_SPREAD_LOG = 0.06       # bid/ask spread allowed for a market to be logged for learning
MAX_SPREAD_PICK = 0.04      # tighter spread required for a market to be recommended
MIN_LIQUIDITY = 200         # open interest or 24h volume (contracts) required
MIN_PRICE, MAX_PRICE = 0.03, 0.97   # ignore markets that are basically decided

# --- Picks email --------------------------------------------------------------------
N_LIKELY = 15               # "most likely to hit" list length
SAFE_MIN_PROB = 0.88        # the safe list only includes picks the BOT rates at least this likely (not Kalshi's price)
LIKELY_MAX_PRICE = 0.92     # a 97c "lock" pays 3c; skip anything that costs more than this
N_VALUE = 10                # "best value" list length
VALUE_MIN_EV = 0.02         # expected profit per $1 contract (after fees) to call it value
N_PARLAY_LEGS = (2, 3)      # build the safest 2- and 3-leg combos from the likely list

# --- Learning -----------------------------------------------------------------------
MIN_TRAIN_ROWS = 150        # a market family needs this many settled rows before it gets its own weights
TEST_FRACTION = 0.25        # newest 25% of history is held out to prove a change actually helps
MIN_IMPROVEMENT = 0.0015    # log-loss gain per prediction the held-out test must show to adopt it
PRIOR_STRENGTH = 8.0        # pulls each family's weights toward its parent (sport -> all markets)
BACKFILL_SNAPSHOT_HOURS = 6 # backfilled rows use the price this many hours before Kalshi's occurrence time
