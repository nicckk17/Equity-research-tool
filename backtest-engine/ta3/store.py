"""Local data store: one Parquet file per symbol per base timeframe, a DuckDB catalogue on top, every other
timeframe resampled from the finest stored base, and a data-quality score per symbol.

Layout: data/store/<universe>/<base>/<SYM>.parquet  (base = "D" for daily history, "1m"/"5m"/"60m"... for intraday)
Commands (python -m ta3 data ...): import (ta2 CSVs -> store), quality, intraday (download), catalogue.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

from . import config as C
from ta2 import data as D2

COLS = ["open", "high", "low", "close", "adj_close", "volume"]
BASE_ORDER = ["1m", "5m", "15m", "30m", "1h", "4h", "D"]       # finest first


# ---------------------------------------------------------------- paths
def _p(universe, base, sym) -> Path:
    d = C.STORE / universe / base
    d.mkdir(parents=True, exist_ok=True)
    return d / (sym.replace("^", "IDX_") + ".parquet")


def bases(universe, sym):
    return [b for b in BASE_ORDER if _p(universe, b, sym).exists()]


def save(df: pd.DataFrame, universe, base, sym, merge=True):
    """Write bars (DatetimeIndex) to the store, merging with what is already there (new rows win)."""
    df = _clean(df)
    p = _p(universe, base, sym)
    if merge and p.exists():
        old = pd.read_parquet(p)
        df = _clean(pd.concat([old, df]))
    df.to_parquet(p)
    return len(df)


def _clean(df):
    df = df.copy()
    df.index = pd.DatetimeIndex(df.index).tz_localize(None) if getattr(df.index, "tz", None) else pd.DatetimeIndex(df.index)
    for c in COLS:
        if c not in df:
            df[c] = df["close"] if c == "adj_close" else np.nan
        df[c] = pd.to_numeric(df[c], errors="coerce")
    p = df[["open", "high", "low", "close"]]
    ok = np.isfinite(p).all(axis=1) & (p > 0).all(axis=1)
    ok &= (df.high >= p[["open", "close"]].max(axis=1)) & (df.low <= p[["open", "close"]].min(axis=1))
    df = df.loc[ok, COLS].sort_index(kind="stable")
    return df[~df.index.duplicated(keep="last")]


# ---------------------------------------------------------------- import ta2 daily CSVs (bars + spent holdout)
def import_ta2(universe="TSX"):
    u = C.UNIVERSES[universe]; rows = []
    for s in list(u["symbols"]) + list(u.get("extra", [])):
        df = D2.load(s, universe, holdout=True)
        if len(df):
            rows.append((s, save(df, universe, "D", s, merge=False)))
    return pd.DataFrame(rows, columns=["symbol", "rows"])


# ---------------------------------------------------------------- load + resample
def load(sym, universe="TSX", tf="D", holdout=False, start=None, end=None) -> pd.DataFrame:
    """Bars for any timeframe. Daily-and-up come from the D base; intraday from the finest intraday base that
    can build tf. holdout=False cuts the spent holdout (same rule as ta2)."""
    want = BASE_ORDER.index(tf) if tf in BASE_ORDER else len(BASE_ORDER)
    have = [b for b in bases(universe, sym) if BASE_ORDER.index(b) <= want]
    if not have:
        return _clean(pd.DataFrame(columns=COLS, index=pd.DatetimeIndex([])))
    base = have[-1] if tf in ("D", "W", "M") and "D" in have else have[0]
    df = pd.read_parquet(_p(universe, base, sym))
    if not holdout and tf in ("D", "W", "M"):
        df = df[df.index < pd.Timestamp(C.HOLDOUT[0])]
    if start is not None:
        df = df[df.index >= pd.Timestamp(start)]
    if end is not None:
        df = df[df.index <= pd.Timestamp(end)]
    return df if tf == base else resample(df, tf)


def resample(df, tf):
    """OHLCV resample. Weekly/monthly bars are labelled with their LAST trading day (the day the bar's close is
    known), so a signal on a weekly bar can never use data from later in that week (no look-ahead)."""
    if df.empty:
        return df
    agg = dict(open="first", high="max", low="min", close="last", adj_close="last", volume="sum")
    if tf in ("W", "M"):
        key = df.index.to_period("W-FRI" if tf == "W" else "M")
        g = df.groupby(key)
        out = g.agg(agg)
        out.index = pd.DatetimeIndex(g.apply(lambda x: x.index[-1]))
    else:
        # intraday: bins anchored at the session open; empty bins dropped
        out = df.resample(C.TF_RULE[tf], label="left", closed="left", origin="start_day",
                          offset="30min" if tf in ("1h", "4h") else None).agg(agg)
    return out.dropna(subset=["open", "high", "low", "close"])


def catalogue():
    """DuckDB view over every Parquet file: one row per symbol x base with rows and date range."""
    import duckdb
    con = duckdb.connect(str(C.DB))
    files = sorted(C.STORE.glob("*/*/*.parquet"))
    rows = []
    for f in files:
        df = pd.read_parquet(f)
        rows.append(dict(universe=f.parts[-3], base=f.parts[-2], symbol=f.stem, rows=len(df),
                         first=df.index.min(), last=df.index.max()))
    cat = pd.DataFrame(rows)
    con.execute("create or replace table catalogue as select * from cat")
    con.close()
    return cat


# ---------------------------------------------------------------- data quality
def quality(df: pd.DataFrame, tf="D") -> dict:
    """Flags that matter for backtests. score 0..1 (1 = clean). bad_open_years: years where open sits exactly on
    the bar's low or high on >20% of bars (normal TSX ~10%, US ~3%) (Yahoo's pre-2005 TSX opens) -> don't trust open-entry tests there."""
    if df.empty:
        return dict(score=0.0, rows=0)
    n = len(df); r = df.close.pct_change()
    zero_vol = float((df.volume.fillna(0) <= 0).mean())
    stale = float((df.close.diff() == 0).rolling(5).sum().ge(5).mean())
    jumps = int((r.abs() > (0.4 if tf in ("D", "W", "M") else 0.2)).sum())
    ratio = (df.adj_close / df.close).replace([np.inf, -np.inf], np.nan)
    adj_breaks = int((ratio.pct_change().abs() > 0.2).sum())
    on_edge = (df.open == df.low) | (df.open == df.high)
    by_year = on_edge.groupby(df.index.year).mean()
    bad_years = [int(y) for y, v in by_year.items() if v > C.BAD_OPEN_SHARE]
    gaps = 0
    if tf == "D":
        bd = pd.bdate_range(df.index[0], df.index[-1])
        gaps = int((len(bd) - n) > 0.05 * len(bd))
    score = 1.0 - min(1.0, 0.5 * zero_vol + 0.5 * stale + 0.02 * jumps + 0.02 * adj_breaks
                      + 0.02 * len(bad_years) + 0.1 * gaps)
    return dict(rows=n, first=str(df.index[0].date()), last=str(df.index[-1].date()), score=round(score, 3),
                zero_vol=round(zero_vol, 4), stale=round(stale, 4), jumps=jumps, adj_breaks=adj_breaks,
                bad_open_years=bad_years, many_gaps=bool(gaps))


def quality_report(universe="TSX", tf="D"):
    u = C.UNIVERSES[universe]; rows = []
    for s in u["symbols"]:
        q = quality(load(s, universe, tf, holdout=True), tf); q["symbol"] = s; rows.append(q)
    rep = pd.DataFrame(rows)
    out = C.RESULTS / "data_quality"; out.mkdir(parents=True, exist_ok=True)
    rep.to_csv(out / f"{universe}_{tf}.csv", index=False)
    return rep


def bad_open_mask(df) -> np.ndarray:
    """True on bars whose year has untrustworthy opens (see quality)."""
    on_edge = (df.open == df.low) | (df.open == df.high)
    share = on_edge.groupby(df.index.year).transform("mean")
    return (share > C.BAD_OPEN_SHARE).to_numpy()


# ---------------------------------------------------------------- intraday downloads (run on Nik's PC)
def fetch_yahoo_intraday(sym, interval="60m", range_="730d") -> pd.DataFrame:
    """Yahoo chart API intraday (free): 60m ~730 days, 15m/5m ~60 days, 1m ~7 days. Same endpoint ta2 uses."""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(sym, safe='')}"
           f"?range={range_}&interval={interval}&includePrePost=false")
    with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as r:
        js = json.load(r)
    res = (js.get("chart", {}).get("result") or [None])[0]
    if not res or not res.get("timestamp"):
        return _clean(pd.DataFrame(columns=COLS, index=pd.DatetimeIndex([])))
    q = res["indicators"]["quote"][0]; tz = res.get("meta", {}).get("exchangeTimezoneName", "UTC")
    idx = pd.to_datetime(res["timestamp"], unit="s", utc=True).tz_convert(tz).tz_localize(None)
    return _clean(pd.DataFrame(dict(open=q["open"], high=q["high"], low=q["low"], close=q["close"],
                                    volume=q["volume"]), index=idx))


def fetch_alpaca(sym, start, end=None, timeframe="1Min", feed="iex") -> pd.DataFrame:
    """Alpaca market-data v2 bars (US only). Keys from env/.env: ALPACA_API_KEY / ALPACA_SECRET_KEY.
    Free plan = IEX feed; SIP needs a paid plan. Times converted to New York."""
    _load_env()
    key, sec = os.environ.get("ALPACA_API_KEY") or os.environ.get("APCA_API_KEY_ID"), \
        os.environ.get("ALPACA_SECRET_KEY") or os.environ.get("APCA_API_SECRET_KEY")
    if not key or not sec:
        raise RuntimeError("Alpaca keys not found (ALPACA_API_KEY / ALPACA_SECRET_KEY in .env)")
    out, token = [], None
    while True:
        qs = f"timeframe={timeframe}&start={pd.Timestamp(start):%Y-%m-%dT%H:%M:%SZ}&limit=10000&adjustment=all&feed={feed}"
        if end:
            qs += f"&end={pd.Timestamp(end):%Y-%m-%dT%H:%M:%SZ}"
        if token:
            qs += f"&page_token={token}"
        req = Request(f"https://data.alpaca.markets/v2/stocks/{sym}/bars?{qs}",
                      headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec})
        with urlopen(req, timeout=30) as r:
            js = json.load(r)
        out += js.get("bars") or []
        token = js.get("next_page_token")
        if not token:
            break
        time.sleep(0.3)
    if not out:
        return _clean(pd.DataFrame(columns=COLS, index=pd.DatetimeIndex([])))
    b = pd.DataFrame(out)
    idx = pd.to_datetime(b.t, utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
    df = pd.DataFrame(dict(open=b.o.values, high=b.h.values, low=b.l.values, close=b.c.values, volume=b.v.values),
                      index=pd.DatetimeIndex(idx))
    # regular session only
    t = df.index.time
    df = df[(t >= pd.Timestamp("09:30").time()) & (t < pd.Timestamp("16:00").time())]
    return _clean(df)


def intraday_update(universe="TSX", source="yahoo", interval="60m", pause=0.6, only=None):
    """Download intraday bars for a universe into the store (merging with history already saved, so the
    intraday archive grows every time this runs). TSX: yahoo only (Alpaca is US-only)."""
    u = C.UNIVERSES[universe]; rep = []
    base = {"60m": "1h", "15m": "15m", "5m": "5m", "1m": "1m", "1Min": "1m", "5Min": "5m"}[interval]
    for s in (only or u["symbols"]):
        try:
            if source == "alpaca":
                df = fetch_alpaca(s.replace("-", "."), start=pd.Timestamp.today() - pd.Timedelta(days=365 * 5),
                                  timeframe=interval)
            else:
                df = fetch_yahoo_intraday(s, interval, {"60m": "730d", "15m": "60d", "5m": "60d", "1m": "7d"}[interval])
            rep.append((s, save(df, universe, base, s)))
        except Exception as ex:
            rep.append((s, f"error: {ex}"))
        print(rep[-1], flush=True); time.sleep(pause)
    return pd.DataFrame(rep, columns=["symbol", "rows"])


def _load_env():
    for p in [Path(".env"), C.ROOT / ".env", C.ROOT.parent / ".env"]:
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip().strip("\"'"))
