"""Every rule of the backtest in one place (v2, 2026-11-03).

Change a number here and every strategy, test and report uses it. Nothing else in ta2 hard-codes
a window, a fee or a sizing rule. Values are the ones Phase 2 (v1) used, so v1 results stay comparable.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # tsx-ta/
DATA = ROOT / "data"
RESULTS = ROOT / "results" / "ta2"
REGISTRY = ROOT / "registry"

# ---------------------------------------------------------------- windows
IS = ("2000-01-01", "2015-12-31")         # choose / tune here only
OOS = ("2016-01-01", "2024-10-31")        # confirm here (never tune)
HOLDOUT = ("2024-11-01", "2026-10-31")    # SPENT: used once for every v1 family. Report it, never choose on it.
FORWARD_START = "2026-11-01"              # the only untouched data left: live paper trading from here
WINDOWS = {"IS": IS, "OOS": OOS, "HO": HOLDOUT}

# ---------------------------------------------------------------- costs (per side)
COST_MAIN = 0.0012      # 0.12% per side: main test
COST_LOW = 0.0005       # 0.05% per side: low-fee sensitivity
STOP_SLIP = 0.0010      # extra 0.10% on stop fills
BORROW = 0.005          # 0.5%/yr borrow on shorts

# ---------------------------------------------------------------- trade rules
MIN_R_ATR = 0.25        # skip a trade whose risk (entry to stop) is under 0.25 ATR
MAX_HOLD = 40           # default time exit in bars (a strategy may set its own)
N_TWINS = 5             # random-entry twins per trade (same stock, side, window, stop width, exit)
TWIN_WARMUP = 60        # twins never enter in a stock's first 60 bars
MIN_BARS = 300          # skip a stock with less history than this

# ---------------------------------------------------------------- statistics
BOOT = 2000             # week-block bootstrap draws
MIN_TRADES = {"IS": 100, "OOS": 50, "HO": 20}   # fewer trades = not judged
P_PASS = 0.05           # Romano-Wolf p (IS) and single p (OOS) must be below this
SEED = 1

# ---------------------------------------------------------------- portfolio
RISK_PER_TRADE = 0.0033 # 0.33% of equity per trade (S53 live "as designed")
MAX_OPEN = 30
NOTIONAL_CAP = 0.20     # one position <= 20% of equity
MAX_GROSS = 1.0         # no margin

# ---------------------------------------------------------------- live bot rails (ta2/bot.py)
MAX_NEW_PER_DAY = 15    # safety rail against a bad data day; S53 signals cluster on market dips
KILL_DRAWDOWN = 0.30    # stop NEW entries past this drawdown (1.5 x S53's worst backtest portfolio drop, -24% IS)
IB_PAPER_PORT = 4002    # IB Gateway paper (TWS paper 7497); live ports are refused by broker.py

# ---------------------------------------------------------------- universes
TSX60 = [
    "RY", "TD", "BNS", "BMO", "CM", "NA", "MFC", "SLF", "GWO", "POW", "IFC", "FFH",
    "BN", "BAM", "ENB", "TRP", "PPL", "SU", "CNQ", "CVE", "IMO", "TOU", "ARX", "CCO",
    "ABX", "AEM", "WPM", "FNV", "K", "TECK-B", "FM", "NTR", "CP", "CNR", "WCN", "TFII",
    "ATD", "L", "MRU", "DOL", "WN", "SAP", "QSR", "CTC-A", "GIB-A", "OTEX", "SHOP",
    "CSU", "BCE", "T", "RCI-B", "FTS", "EMA", "H", "CAE", "CCL-B", "WSP", "STN", "TRI",
    "CLS",
]
TSX_EXTRA = ["XIU.TO", "^GSPTSE", "XFN.TO", "XEG.TO", "XMA.TO", "XIT.TO", "XRE.TO", "XUT.TO", "XGD.TO"]
# US cold-test universe: 100 largest S&P 500 companies (2026-10-27) with Yahoo history back to 2000.
US100 = [
    "NVDA", "AAPL", "MSFT", "AMZN", "LLY", "BRK-B", "MU", "WMT", "AMD", "JPM",
    "XOM", "JNJ", "INTC", "CVX", "CSCO", "COST", "ORCL", "KO", "PG", "UNH",
    "BAC", "MRK", "CAT", "HD", "AMAT", "GE", "LRCX", "MS", "TXN", "GS",
    "RTX", "TMO", "WFC", "AMGN", "IBM", "LIN", "AXP", "ADI", "C", "KLAC",
    "GILD", "QCOM", "APH", "DIS", "BLK", "PEP", "VZ", "UNP", "ABT", "COP",
    "MCD", "NEE", "DE", "PFE", "DHR", "WELL", "SCHW", "TJX", "ETN", "WDC",
    "LMT", "T", "CB", "SPGI", "BA", "PGR", "VRTX", "BMY", "PLD", "COF",
    "MO", "MDT", "SBUX", "NEM", "CVS", "ADP", "SYK", "PH", "MCK", "VLO",
    "BKNG", "LOW", "GLW", "SO", "MAR", "TT", "BNY", "DUK", "ADBE", "GD",
    "CSX", "CDNS", "FCX", "JCI", "USB", "EMR", "WM", "SNPS", "MRSH", "PNC",
]
UNIVERSES = {
    "TSX": dict(dir="p2", symbols=[t + ".TO" for t in TSX60], bench="XIU.TO", extra=TSX_EXTRA),
    "US": dict(dir="p2us", symbols=list(US100), bench="SPY", extra=["SPY"]),
}
# Delisted names: kept in backtests (their history is real), dropped from live scanning.
DELISTED = {"ARX.TO": "ARC Resources: acquired by Shell, delisted Sep 2026"}
