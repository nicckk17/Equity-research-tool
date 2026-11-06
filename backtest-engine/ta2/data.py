"""Data connectors: Yahoo daily bars (+ earnings dates), FRED/CAD T-bills, one clean loader.

Layout (unchanged from v1, so no migration):  data/<p2|p2us>/bars/<SYM>.csv   (to 2024-10-31)
                                               data/<p2|p2us>/holdout/<SYM>.csv (2024-11-01 on)
                                               data/<p2|p2us>/earnings/<SYM>.csv
Columns: date, open, high, low, close, adj_close, volume. OHLC are split-adjusted, NOT dividend-adjusted
(patterns use traded prices); adj_close includes dividends (for buy-and-hold benchmarks).

Data rules (learned the hard way in v1): never raise on gaps. Empty files (ARX: Yahoo has no history)
load as empty frames; invalid OHLC rows are dropped; duplicates keep the last; callers mark-to-market
with the last known price and exit on the next available bar.

  python -m ta2 data update [--universe US] [--only RY.TO,TD.TO]
"""
from __future__ import annotations
import json, time
from urllib.parse import quote
from urllib.request import Request, urlopen
import numpy as np
import pandas as pd
from . import config as C

COLS = ["date", "open", "high", "low", "close", "adj_close", "volume"]


def _dir(universe):
    return C.DATA / C.UNIVERSES[universe]["dir"]


def _path(kind, sym, universe="TSX"):
    d = _dir(universe) / kind
    d.mkdir(parents=True, exist_ok=True)
    return d / (sym.replace("^", "IDX_") + ".csv")


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Valid OHLC rows only, sorted, unique dates."""
    if df is None or df.empty:
        return pd.DataFrame({c: pd.Series(dtype="datetime64[ns]" if c == "date" else float) for c in COLS})
    df = df.copy()
    df["date"] = pd.DatetimeIndex(pd.to_datetime(df["date"], errors="coerce")).tz_localize(None).normalize()
    for c in COLS[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    p = df[["open", "high", "low", "close"]]
    ok = df.date.notna() & np.isfinite(p).all(axis=1) & (p > 0).all(axis=1)
    ok &= (df.high >= p[["open", "close"]].max(axis=1)) & (df.low <= p[["open", "close"]].min(axis=1))
    df = df.loc[ok, COLS].sort_values("date", kind="stable")
    return df.drop_duplicates("date", keep="last").reset_index(drop=True)


# ---------------------------------------------------------------- downloads
def fetch_chart(sym: str, range_: str = "max", timeout: float = 10) -> pd.DataFrame:
    """Yahoo chart API directly (no yfinance needed; works where yfinance is blocked).
    Same numbers as yfinance auto_adjust=False: OHLC split-adjusted, adj_close dividend-adjusted."""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(sym, safe='')}"
           f"?range={range_}&interval=1d&includeAdjustedClose=true&events=div%2Csplit")
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=timeout) as r:
                js = json.load(r)
            break
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1 + attempt)
    res = (js.get("chart", {}).get("result") or [None])[0]
    if not res or not res.get("timestamp"):
        return clean(None)
    q = res["indicators"]["quote"][0]
    adj = (res["indicators"].get("adjclose") or [{}])[0].get("adjclose", q["close"])
    tz = res.get("meta", {}).get("exchangeTimezoneName", "UTC")
    dates = pd.to_datetime(res["timestamp"], unit="s", utc=True).tz_convert(tz).tz_localize(None).normalize()
    df = pd.DataFrame(dict(date=dates, open=q["open"], high=q["high"], low=q["low"], close=q["close"],
                           adj_close=adj, volume=q["volume"]))
    return clean(df)


def fetch_earnings(sym: str) -> pd.DataFrame:
    try:
        import yfinance as yf
        e = yf.Ticker(sym).get_earnings_dates(limit=100)
    except Exception:
        e = None
    if e is None or len(e) == 0:
        return pd.DataFrame(columns=["date"])
    return pd.DataFrame({"date": pd.to_datetime(e.index).tz_localize(None).normalize()}).drop_duplicates()


def update(universe="TSX", only=None, pause=0.5, earnings_too=True):
    """Download full history; split at the holdout date into bars/ and holdout/ (same as v1)."""
    u = C.UNIVERSES[universe]
    syms = only or (u["symbols"] + u["extra"])
    cut = pd.Timestamp(C.HOLDOUT[0]); rep = []
    for s in syms:
        try:
            df = fetch_chart(s)
            if df.empty:
                rep.append((s, 0, "no data")); print(rep[-1], flush=True); continue
            df[df.date < cut].to_csv(_path("bars", s, universe), index=False)
            df[df.date >= cut].to_csv(_path("holdout", s, universe), index=False)
            if earnings_too and s in u["symbols"]:
                fetch_earnings(s).to_csv(_path("earnings", s, universe), index=False)
            rep.append((s, len(df), f"{df.date.min():%Y-%m-%d} to {df.date.max():%Y-%m-%d}"))
        except Exception as ex:
            rep.append((s, 0, f"error: {ex}"))
        print(rep[-1], flush=True); time.sleep(pause)
    return pd.DataFrame(rep, columns=["symbol", "rows", "range"])


# ---------------------------------------------------------------- loaders
def _read(path):
    if not path.exists() or path.stat().st_size == 0:
        return clean(None)
    try:
        return clean(pd.read_csv(path))
    except pd.errors.EmptyDataError:
        return clean(None)


def load(sym: str, universe="TSX", holdout=False) -> pd.DataFrame:
    """Daily bars with a DatetimeIndex. holdout=True appends the (spent) holdout period."""
    frames = [_read(_path("bars", sym, universe))]
    if holdout:
        frames.append(_read(_path("holdout", sym, universe)))
    df = clean(pd.concat(frames, ignore_index=True)) if len(frames) > 1 else frames[0]
    df = df.set_index("date")
    df.index = pd.DatetimeIndex(df.index, name="date")
    return df


def earnings(sym: str, universe="TSX") -> pd.Series:
    p = _path("earnings", sym, universe)
    try:
        d = pd.read_csv(p)["date"] if p.exists() and p.stat().st_size else []
    except pd.errors.EmptyDataError:
        d = []
    return pd.Series(pd.DatetimeIndex(pd.to_datetime(d)).normalize().unique().sort_values(), dtype="datetime64[ns]")


def closes(universe="TSX", holdout=False, adjusted=False) -> pd.DataFrame:
    """dates x symbols close matrix (forward-filled), for portfolios and benchmarks."""
    col = "adj_close" if adjusted else "close"
    m = {}
    for s in C.UNIVERSES[universe]["symbols"]:
        d = load(s, universe, holdout)
        if len(d):
            m[s.replace(".TO", "")] = d[col]
    return pd.concat(m, axis=1).sort_index().ffill()


def tbill(universe="TSX") -> pd.Series:
    """Annual T-bill rate in % (CAD 90-day / US 3-month), daily, forward-filled."""
    f = C.DATA / "p2" / ("tbill_cad_90d.csv" if universe == "TSX" else "tbill_us_3m.csv")
    d = pd.read_csv(f)
    d.columns = ["date", "rate"] + list(d.columns[2:])
    return pd.Series(pd.to_numeric(d["rate"], errors="coerce").values, index=pd.to_datetime(d["date"])).ffill()
