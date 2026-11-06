"""Order-flow tools (ATAS-style features, own build).

From bars (works now on stored minute/hour bars):  session_vwap (+ bands), anchored_vwap, relative_volume,
volume_profile (POC / value area), session_profiles.
From ticks (needs tick data with trade side or quotes; e.g. futures from Databento, or IBKR tick history):
classify_ticks (Lee-Ready), footprint (bid x ask volume per price per bar), bar_delta (delta, CVD),
imbalances (diagonal, stacked), absorption, big_trades.
Bars: DatetimeIndex + open/high/low/close/volume. Ticks: DatetimeIndex + price/size [+ side or bid/ask]."""
from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------- from bars
def session_vwap(bars, k=(1.0, 2.0)):
    """Session VWAP (resets daily) with volume-weighted standard-deviation bands."""
    tp = (bars.high + bars.low + bars.close) / 3; v = bars.volume.astype(float); day = bars.index.normalize()
    cv = v.groupby(day).cumsum(); vwap = (tp * v).groupby(day).cumsum() / cv
    var = (tp ** 2 * v).groupby(day).cumsum() / cv - vwap ** 2
    sd = np.sqrt(var.clip(lower=0)); out = pd.DataFrame(dict(vwap=vwap))
    for x in k:
        out[f"upper_{x}"] = vwap + x * sd; out[f"lower_{x}"] = vwap - x * sd
    return out


def anchored_vwap(bars, anchor):
    """VWAP from a chosen bar (e.g. earnings day, swing low) forward; NaN before the anchor."""
    tp = (bars.high + bars.low + bars.close) / 3; v = bars.volume.astype(float)
    m = bars.index >= pd.Timestamp(anchor)
    out = pd.Series(np.nan, index=bars.index)
    out[m] = (tp[m] * v[m]).cumsum() / v[m].cumsum()
    return out


def relative_volume(bars, lookback=20):
    """Volume / average volume of the same time-of-day bar over the previous `lookback` sessions."""
    v = bars.volume.astype(float); tod = bars.index.time
    if len(set(tod)) == 1:
        return v / v.rolling(lookback).mean().shift(1)
    avg = v.groupby(tod).transform(lambda s: s.rolling(lookback, min_periods=5).mean().shift(1))
    return v / avg


def volume_profile(bars, bins=50, value_area=0.70):
    """Volume at price (each bar's volume spread evenly over its low..high), POC and value area."""
    lo, hi = float(bars.low.min()), float(bars.high.max())
    edges = np.linspace(lo, hi, bins + 1); vol = np.zeros(bins)
    for l, h, v in zip(bars.low.to_numpy(), bars.high.to_numpy(), bars.volume.to_numpy(float)):
        a = np.clip(np.searchsorted(edges, l, "right") - 1, 0, bins - 1)
        b = np.clip(np.searchsorted(edges, h, "right") - 1, 0, bins - 1)
        vol[a:b + 1] += v / (b - a + 1)
    centres = (edges[:-1] + edges[1:]) / 2; p = int(vol.argmax()); i = j = p; tot = vol.sum(); acc = vol[p]
    while acc < value_area * tot and (i > 0 or j < bins - 1):
        up = vol[j + 1] if j < bins - 1 else -1; dn = vol[i - 1] if i > 0 else -1
        if up >= dn:
            j += 1; acc += vol[j]
        else:
            i -= 1; acc += vol[i]
    return dict(prices=centres, volume=vol, poc=float(centres[p]), vah=float(centres[j]), val=float(centres[i]))


def session_profiles(bars, bins=50, value_area=0.70):
    """One volume profile per session: POC, VAH, VAL, total volume (use the PREVIOUS session's levels live)."""
    rows = {}
    for d, g in bars.groupby(bars.index.normalize()):
        p = volume_profile(g, bins, value_area)
        rows[d] = dict(poc=p["poc"], vah=p["vah"], val=p["val"], total_volume=float(g.volume.sum()))
    return pd.DataFrame.from_dict(rows, orient="index")


# ---------------------------------------------------------------- from ticks
def classify_ticks(ticks):
    """+1 buyer-initiated / -1 seller-initiated: given side, else quote rule vs mid, else tick rule (Lee-Ready)."""
    if "side" in ticks:
        return ticks.side.astype(int)
    px = ticks.price.to_numpy(float)
    d = np.sign(np.diff(px, prepend=px[0])); d[0] = 1
    tick = pd.Series(np.where(d == 0, np.nan, d), index=ticks.index).ffill().fillna(1)
    if {"bid", "ask"} <= set(ticks.columns):
        mid = (ticks.bid + ticks.ask) / 2
        q = np.sign(ticks.price - mid)
        return pd.Series(np.where(q != 0, q, tick), index=ticks.index).astype(int)
    return tick.astype(int)


def footprint(ticks, bar_rule="5min", tick_size=0.01):
    """Bid x ask volume per price level per bar: bid_vol = sold into the bid, ask_vol = bought at the ask."""
    s = classify_ticks(ticks)
    df = pd.DataFrame(dict(bar_time=ticks.index.floor(bar_rule), price_level=np.round(ticks.price / tick_size) * tick_size,
                           ask_vol=np.where(s > 0, ticks["size"], 0.0), bid_vol=np.where(s < 0, ticks["size"], 0.0)))
    fp = df.groupby(["bar_time", "price_level"])[["bid_vol", "ask_vol"]].sum()
    fp["delta"] = fp.ask_vol - fp.bid_vol
    return fp


def bar_delta(ticks, bar_rule="5min"):
    """Per bar: volume, buy/sell volume, delta, cumulative delta (all sample and per session)."""
    s = classify_ticks(ticks); sz = ticks["size"].astype(float)
    g = pd.DataFrame(dict(volume=sz, buy_vol=sz.where(s > 0, 0.0), sell_vol=sz.where(s < 0, 0.0))).groupby(ticks.index.floor(bar_rule)).sum()
    g["delta"] = g.buy_vol - g.sell_vol; g["cvd"] = g.delta.cumsum()
    g["cvd_session"] = g.delta.groupby(g.index.normalize()).cumsum()
    return g


def imbalances(fp, ratio=3.0, stack=3):
    """Diagonal imbalances (ask at p vs bid one tick below; bid at p vs ask one tick above) and stacked runs."""
    rows = []
    for bt, g in fp.groupby(level=0):
        g = g.droplevel(0).sort_index(); lv = g.index.to_numpy(float)
        if len(lv) < 2:
            continue
        tk = np.min(np.diff(lv)); ask = g.ask_vol; bid = g.bid_vol
        for kind, a, b, shift in (("buy", ask, bid, -tk), ("sell", bid, ask, tk)):
            ref = b.reindex(np.round(lv + shift, 10), fill_value=0.0).to_numpy()
            hit = (a.to_numpy() > 0) & (a.to_numpy() >= ratio * np.maximum(ref, 1e-9))
            run = np.zeros(len(lv), int); c = 0
            for i, h in enumerate(hit):
                c = c + 1 if h else 0; run[i] = c
            stacked = np.zeros(len(lv), bool)
            for i in np.flatnonzero(run >= stack):
                stacked[i - run[i] + 1:i + 1] = True
            for i in np.flatnonzero(hit):
                rows.append(dict(bar_time=bt, price_level=lv[i], kind=kind, stacked=bool(stacked[i])))
    return pd.DataFrame(rows)


def absorption(bars_delta, bars, z=2.0, lookback=50):
    """Heavy aggression (|delta| z-score >= z vs past bars) that did not move price (|return| z-score < 0.5)."""
    d = bars_delta.delta.reindex(bars.index).fillna(0.0); r = bars.close.pct_change()
    zd = (d.abs() - d.abs().rolling(lookback).mean().shift(1)) / d.abs().rolling(lookback).std().shift(1)
    zr = (r.abs() - r.abs().rolling(lookback).mean().shift(1)) / r.abs().rolling(lookback).std().shift(1)
    return (zd >= z) & (zr < 0.5)


def big_trades(ticks, quantile=0.995):
    """Prints at or above the size quantile, with their side."""
    cut = ticks["size"].quantile(quantile); m = ticks["size"] >= cut
    return pd.DataFrame(dict(price=ticks.price[m], size=ticks["size"][m], side=classify_ticks(ticks)[m]))
