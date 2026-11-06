"""S31 RSI divergence + closing trigger. TIER: WEAK (fails US 2000-15). Signal code from v1."""

import numpy as np
from .common import std_exits
import pandas as pd

OUT = "S31"
CHUNK = 10
SIDES = (1, -1)
MODES = [0, 1]
BUFS = [0.1, 0.5]
FLAGS = ["sp5", "sp10", "sp25", "rsi", "two3", "candle",
         "double", "ema200", "rejection", "vol"]


def specs():
    return [(dict(spacing=f"3-{spacing}", indicator=indicator, trigger=family,
                  confluence=confluence), family,
             (f"sp{spacing}", indicator) + (() if confluence == "none" else (confluence,)))
            for spacing in (5, 10, 25) for indicator in ("rsi", "two3")
            for family in ("alert", "range")
            for confluence in ("none", "double", "ema200", "rejection")]


NAMED = {
    "as taught (RSI, 3-10 bars, alert break, next open)":
        dict(fam="alert", flags=("sp10", "rsi"), target="2R", mode=1, buf=0.1),
    "as traded (RSI, 3-25 bars, alert break close)":
        dict(fam="alert", flags=("sp25", "rsi"), target="2R", mode=0, buf=0.1),
    "AK (2 of 3, 3-25 bars, confirming candle)":
        dict(fam="alert", flags=("sp25", "two3", "candle"), target="2R", mode=1, buf=0.1),
}
LADDER = dict(
    base=dict(fam="alert", flags=("sp25", "rsi"), target="2R", mode=1, buf=0.1),
    steps=[("base divergence + alert break", {}, True),
           ("3-10 bars alone", {"add": "sp10"}, False),
           ("3-5 bars alone", {"add": "sp5"}, False),
           ("range break alone", {"fam": "range"}, False),
           ("+ confirming candle", {"add": "candle"}, True),
           ("+ rejection at second pivot", {"add": "rejection"}, True),
           ("double bottom/top alone", {"add": "double"}, False),
           ("200 EMA location alone", {"add": "ema200"}, False)])


def signals(df, ctx):
    """One row per second-pivot/trigger episode. t is the observable break close."""
    columns = ["t", "side", "anchor", "A", "opp", "fam"] + FLAGS + ["p1", "p2", "confirmed", "level"]
    if df.empty:
        return pd.DataFrame(columns=columns)
    o, h, l, c = (df[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    n = len(c)
    a = np.asarray(ctx["atr"], dtype=float)
    r = np.asarray(ctx["rsi"], dtype=float)
    if a.shape != (n,) or r.shape != (n,):
        raise ValueError("atr and rsi must align with df")
    close = pd.Series(c)
    macd = (close.ewm(span=12, adjust=False, min_periods=12).mean()
            - close.ewm(span=26, adjust=False, min_periods=26).mean()).to_numpy()
    ll = pd.Series(l).rolling(14).min()
    hh = pd.Series(h).rolling(14).max()
    stoch = ((100 * (close - ll) / (hh - ll)).rolling(3).mean()).to_numpy()
    ema = close.ewm(span=200, adjust=False, min_periods=200).mean().to_numpy()
    volume = df.volume if "volume" in df else pd.Series(np.nan, index=df.index)
    volmean = volume.rolling(10).mean().shift(1).to_numpy()
    v = volume.to_numpy(dtype=float)
    good = (np.isfinite(o) & np.isfinite(h) & np.isfinite(l) & np.isfinite(c)
            & (h >= np.maximum(o, c)) & (l <= np.minimum(o, c)))
    rows = []
    for side in SIDES:
        # Work in bullish coordinates. Indicators reverse under price mirroring.
        low, high, cl, op = (l, h, c, o) if side == 1 else (-h, -l, -c, -o)
        osc = (side * r, side * macd, side * stoch)
        pivots, pending = [], {}
        for t in range(n):
            if not good[t]:
                pivots, pending = [], {}
                continue
            pivots = [p for p in pivots if t - 1 - p <= 25]
            j = t - 1
            # Strength 1 strict pivot, observable only at j+1.
            if t >= 2 and good[j-1:j+2].all() and low[j] < low[j-1] and low[j] < low[t]:
                candidate = None
                for p in reversed(pivots):
                    if not 3 <= j - p <= 25 or low[j] >= low[p]:
                        continue
                    votes = [bool(np.isfinite(x[p]) and np.isfinite(x[j]) and x[j] > x[p]) for x in osc]
                    if votes[0] or sum(votes) >= 2:
                        candidate = (p, votes)
                        break
                if candidate is not None:
                    p, votes = candidate
                    # New divergence supersedes any older untriggered setup.
                    pending = {}
                    for fam, level in (("alert", high[j]), ("range", np.max(high[p:j+1]))):
                        pending[fam] = (p, j, t, level, votes)
                pivots.append(j)
            for fam, setup in list(pending.items()):
                p, j, confirmed, level, votes = setup
                if t - j > 10 or low[t] < low[j]:
                    del pending[fam]
                    continue
                if cl[t] <= level:
                    continue
                # First closing break consumes setup even if ATR/risk unavailable.
                del pending[fam]
                if not np.isfinite(a[t]) or a[t] <= 0:
                    continue
                span = high[j] - low[j]
                flags = dict(sp5=j-p <= 5, sp10=j-p <= 10, sp25=True,
                             rsi=votes[0], two3=sum(votes) >= 2,
                             candle=cl[t] > op[t],
                             double=np.isfinite(a[j]) and abs(low[j]-low[p]) <= a[j],
                             ema200=np.isfinite(ema[j]) and np.isfinite(a[j]) and abs(side*ema[j]-low[j]) <= a[j],
                             rejection=span > 0 and min(op[j], cl[j])-low[j] >= 0.5*span,
                             vol=np.isfinite(v[t]) and np.isfinite(volmean[t]) and v[t] > volmean[t])
                rows.append(dict(t=t, side=side, anchor=side*low[j], A=a[t], opp=np.nan,
                                 fam=fam, p1=p, p2=j, confirmed=confirmed, level=side*level, **flags))
    result = pd.DataFrame(rows, columns=columns).sort_values(["t", "side", "fam"], kind="stable").reset_index(drop=True)
    result[FLAGS] = result[FLAGS].astype(bool)
    result.attrs["invalid_ohlc_rows_reset"] = int((~good).sum())
    if "calendar" in ctx:
        cal = pd.DatetimeIndex(ctx["calendar"])
        result.attrs["missing_calendar_bars"] = int(len(cal[(cal >= df.index[0]) & (cal <= df.index[-1])].difference(df.index)))
    return result


# ------------------------------------------------------------ v2 adapter
TIER = "weak"
EVIDENCE = ("as traded: TSX OOS +36 R/yr (p .009), IS +13 (p .08); IS pick 3 (2 of 3, double bottom, close entry): "
            "TSX IS +16 (.014), OOS +24 (.016), US OOS +49 (.006) but US IS +11 (p .23). Works in bull decades only.")
EXITS = std_exits(["1.5R", "2R"])
TARGETS = list(EXITS)
KEEP = {
    "as traded: RSI, 3-25 bars, alert break at close, 2R": dict(fam="alert", flags=("sp25", "rsi"), target="2R", mode=0, buf=0.1, sides=(1,)),
    "IS pick 3: 2 of 3 indicators, double bottom, close entry, 2R": dict(fam="alert", flags=("sp25", "two3", "double"), target="2R", mode=0, buf=0.1, sides=(1,)),
}
LIVE = "IS pick 3: 2 of 3 indicators, double bottom, close entry, 2R"
