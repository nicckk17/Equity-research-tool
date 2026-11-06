"""ta3 settings. Every rule of ta2 (windows, fees, slippage, twins, sizing, universes) is inherited from
ta2/config.py unchanged, so ta3 results stay comparable with v1 and v2. Only what ta3 adds lives here."""
from pathlib import Path
from ta2.config import *          # noqa: F401,F403  (IS, OOS, HOLDOUT, COST_MAIN, N_TWINS, UNIVERSES, ...)
from ta2 import config as _C

ROOT = _C.ROOT                                  # tsx-ta/
STORE = ROOT / "data" / "store"                 # Parquet store: STORE/<universe>/<tf>/<SYM>.parquet
DB = ROOT / "data" / "store.duckdb"             # DuckDB catalogue over the Parquet files
RESULTS = ROOT / "results" / "ta3"
LEDGER = RESULTS / "trial_ledger.csv"           # every config ever graded (feeds deflated Sharpe)
V1_TRIALS = 79_310                              # configs graded in v1 (docs/all_configs_tested.csv.gz)

# ---------------------------------------------------------------- timeframes
# pandas resample rule per timeframe; intraday bars are built from the finest stored base.
TF_RULE = {"1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min", "1h": "60min", "4h": "240min",
           "D": "1D", "W": "W-FRI", "M": "ME"}
INTRADAY = ("1m", "5m", "15m", "30m", "1h", "4h")
BARS_PER_YEAR = {"1m": 252 * 390, "5m": 252 * 78, "15m": 252 * 26, "30m": 252 * 13, "1h": 252 * 7,
                 "4h": 252 * 2, "D": 252, "W": 52, "M": 12}
# Daily/weekly use the v1 windows. Intraday history is short (Yahoo 60m ~2 yrs), so windows are by share
# of the sample: first 60% = IS (choose), last 40% = OOS (confirm). Holdout stays spent.
INTRADAY_IS_SHARE = 0.6
MIN_BARS_TF = {"D": 300, "W": 150, "M": 60}     # intraday: 300

# ---------------------------------------------------------------- sweeps
MAX_GRID = 600            # full-grid cap; bigger grids are sampled (seeded) down to this
PLATEAU_STEP = 1          # neighbours = +/- this many steps on each knob
PLATEAU_KEEP = 0.70       # a neighbour "holds" if it keeps >= 70% of the cell's metric (v1 best-practice rule)
SCORE = "edge"            # cell metric for heatmaps/plateau: edge vs random twins (R/trade, after main costs)

# ---------------------------------------------------------------- walk-forward
WF_TRAIN_YEARS = 5        # daily/weekly: fit on 5 years ...
WF_TEST_YEARS = 1         # ... trade the next 1 year, roll by 1 year
WF_INTRADAY_FOLDS = 5     # intraday: anchored folds by share of sample

# ---------------------------------------------------------------- Monte Carlo
MC_SIMS = 5000
MC_BLOCK_DAYS = 63        # 3-month blocks (same as v1 S53 check)

# ---------------------------------------------------------------- data quality
BAD_OPEN_SHARE = 0.20     # a year is "bad opens" if open == low/high on >20% of bars (TSX normal ~10%, 2000-04 ~25-34%)
