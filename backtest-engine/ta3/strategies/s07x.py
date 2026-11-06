"""S07X kept long confirmation setup; default = ta2 LIVE, including close entry."""
from __future__ import annotations

import numpy as np
import pandas as pd
from numba import njit

from ta3.knobs import Knob
from ta2.indicators import bollinger, stoch_k
from ta2.strategies.common import EXIT_PANEL

KEY = "S07X"
NAME = "Slingshot high confirmation"
SIDE = 1
TIMEFRAMES = ["1h", "D", "W"]
EPISODE_GAP = 5
KNOBS = {
    "bb_bars": Knob(20, [15, 18, 20, 22, 25], "signal", "Bollinger lookback"),
    "bb_sd": Knob(2.5, [2.0, 2.25, 2.5, 2.75, 3.0], "signal", "lower band SD multiple"),
    "stoch_bars": Knob(14, [10, 12, 14, 16, 20], "signal", "stochastic lookback"),
    "stoch_smooth": Knob(3, [1, 2, 3, 4, 5], "signal", "stochastic smoothing"),
    "stoch_max": Knob(30, [10, 20, 25, 30, 35], "signal", "oversold threshold"),
    "required": Knob('2', ['2', '3', '3+candle'], "signal", "votes required; independently debounced"),
    "gap": Knob(5, [3, 4, 5, 7, 10], "signal", "preceding raw qualification suppression window"),
    "support_ma": Knob(50, [34, 40, 50, 60, 75], "signal", "support SMA period"),
    "strength": Knob(5, [3, 4, 5, 6, 7], "signal", "pivot confirmation strength"),
    "pivot_bars": Knob(252, [126, 189, 252, 315], "signal", "confirmed low retention"),
    "ma_tol": Knob(0.5, [0.25, 0.4, 0.5, 0.75, 1.0], "signal", "support proximity in ATR"),
    "ma_look": Knob(50, [30, 40, 50, 60, 75], "signal", "prior MA touch episode window"),
    "ma_count": Knob(2, [1, 2, 3, 4], "signal", "minimum prior MA touch episodes"),
    "horizontal_gap": Knob(10, [5, 8, 10, 15, 20], "signal", "minimum horizontal pivot spacing"),
    "horizontal_count_min": Knob(3, [2, 3, 4, 5], "signal", "minimum horizontal support pivots"),
    "double_gap": Knob(10, [5, 8, 10, 15, 20], "signal", "minimum double-bottom spacing"),
    "double_age": Knob(120, [60, 90, 120, 150, 180], "signal", "maximum double-bottom age"),
    "double_tol": Knob(0.02, [0.01, 0.015, 0.02, 0.025, 0.03], "signal", "double-bottom relative tolerance"),
    "fib_impulse": Knob(0.05, [0.03, 0.04, 0.05, 0.075, 0.1], "signal", "minimum Fibonacci impulse"),
    "fib_age": Knob(252, [126, 189, 252, 315], "signal", "Fibonacci leg expiry"),
    "fib_a": Knob(0.5, [0.382, 0.45, 0.5, 0.55], "signal", "first Fibonacci retracement"),
    "fib_b": Knob(0.618, [0.55, 0.6, 0.618, 0.65, 0.7], "signal", "second Fibonacci retracement"),
    "pin_ratio": Knob(2.0, [1.5, 2.0, 2.5, 3.0], "signal", "pin wick/body ratio"),
    "top_fraction": Knob(0.3333333333333333, [0.25, 0.3333333333333333, 0.4, 0.5], "signal", "maximum close distance from high / range"),
    "body_min": Knob(0.6, [0.4, 0.5, 0.6, 0.7, 0.8], "signal", "full candle body/range minimum"),
    "buf": Knob(0.1, [0.05, 0.1, 0.3, 0.5], "stop", "setup-low stop buffer in ATR"),
    "exit": Knob('2R', ['2R', 'half1R_trail2atr', 'trail2atr', 'time10'], "exit", "exit rule; includes both kept variants"),
    "target_R": Knob(2.0, [1.5, 2.0, 2.5, 3.0], "exit", "fixed profit target in R"),
    "half_R": Knob(1.0, [0.5, 1.0, 1.5, 2.0], "exit", "half position profit level in R"),
    "trail_atr": Knob(2.0, [1.5, 2.0, 2.5, 3.0], "exit", "chandelier ATR multiple"),
    "time_bars": Knob(10, [5, 8, 10, 15, 20], "exit", "timed exit bars"),
    "max_hold": Knob(60, [40, 50, 60, 80], "exit", "hard holding limit"),
    "mode": Knob(0, [0, 1], "entry", "signal close or next open"),
}
SIGNAL_KNOBS = tuple(name for name, knob in KNOBS.items() if knob.part == "signal")


@njit(cache=False)
def _features(op, hi, lo, cl, atr, sma50, strength, pivot_bars, ma_tol,
              ma_look, ma_count, horizontal_gap, horizontal_count_min,
              double_gap, double_age, double_tol, fib_impulse, fib_age,
              fib_a, fib_b, pin_ratio, top_fraction, body_min):
    """Causal support/candle features in the long orientation."""
    n = len(cl)

    pivots = np.empty(pivot_bars + 1, dtype=np.int64)
    pivot_count = 0

    support = np.zeros((n, 4), dtype=np.bool_)
    candles = np.zeros((n, 3), dtype=np.bool_)
    ma_touch = np.zeros(n, dtype=np.bool_)
    episode_prefix = np.zeros(n + 1, dtype=np.int64)

    for t in range(n):
        valid_atr = np.isfinite(atr[t]) and atr[t] > 0.0

        if valid_atr and np.isfinite(sma50[t]):
            ma_touch[t] = (
                abs(lo[t] - sma50[t]) <= ma_tol * atr[t]
                and cl[t] >= sma50[t]
            )
        starts_episode = ma_touch[t] and (
            t == 0 or not ma_touch[t - 1]
        )
        episode_prefix[t + 1] = (
            episode_prefix[t] + int(starts_episode)
        )

        body = cl[t] - op[t]
        candle_range = hi[t] - lo[t]
        top_third = (
            candle_range > 0.0
            and cl[t] >= hi[t] - (candle_range / 3.0 if top_fraction == 1.0 / 3.0
                                  else candle_range * top_fraction)
        )

        candles[t, 0] = (
            body > 0.0
            and op[t] - lo[t] >= pin_ratio * body
            and top_third
        )
        candles[t, 1] = (
            t > 0
            and cl[t - 1] < op[t - 1]
            and body > 0.0
            and op[t] <= cl[t - 1]
            and cl[t] >= op[t - 1]
        )
        candles[t, 2] = (
            body > 0.0
            and body >= body_min * candle_range
            and top_third
        )

    last_low_j = -1
    last_low = np.nan
    fib_active = False
    fib_p = -1
    fib_low = np.nan
    fib_high = np.nan

    for t in range(n):
        kept = 0
        for i in range(pivot_count):
            j = pivots[i]
            if t - j <= pivot_bars:
                pivots[kept] = j
                kept += 1
        pivot_count = kept

        if t >= strength + strength:
            q = t - strength
            is_high = True
            is_low = True
            for b in range(q - strength, t + 1):
                if hi[b] > hi[q]:
                    is_high = False
                if lo[b] < lo[q]:
                    is_low = False

            if is_high:
                fib_active = False
                if last_low_j >= 0 and last_low_j < q:
                    height = hi[q] - last_low
                    denominator = abs(last_low)
                    if (
                        denominator > 0.0
                        and height > 0.0
                        and height / denominator >= fib_impulse
                    ):
                        fib_active = True
                        fib_p = q
                        fib_low = last_low
                        fib_high = hi[q]
                        for b in range(q + 1, t + 1):
                            if lo[b] <= fib_low or hi[b] > fib_high:
                                fib_active = False
                                break

            if is_low:
                pivots[pivot_count] = q
                pivot_count += 1
                last_low_j = q
                last_low = lo[q]

        if fib_active:
            if (
                t - fib_p > fib_age
                or lo[t] <= fib_low
                or hi[t] > fib_high
            ):
                fib_active = False

        if not np.isfinite(atr[t]) or atr[t] <= 0.0:
            continue

        tolerance = ma_tol * atr[t]

        if t >= ma_look and ma_touch[t]:
            prior_episodes = (
                episode_prefix[t] - episode_prefix[t - ma_look]
            )
            support[t, 0] = prior_episodes >= ma_count

        horizontal_count = 0
        newest_selected = -1

        for i in range(pivot_count - 1, -1, -1):
            j = pivots[i]

            if abs(lo[t] - lo[j]) <= tolerance:
                if newest_selected < 0 or newest_selected - j >= horizontal_gap:
                    horizontal_count += 1
                    newest_selected = j

            age = t - j
            denominator = abs(lo[j])
            if (
                age >= double_gap
                and age <= double_age
                and denominator > 0.0
                and abs(lo[t] - lo[j]) / denominator <= double_tol
            ):
                support[t, 2] = True

        support[t, 1] = horizontal_count >= horizontal_count_min

        if fib_active:
            height = fib_high - fib_low
            fib50 = fib_high - fib_a * height
            fib618 = fib_high - fib_b * height
            support[t, 3] = (
                abs(lo[t] - fib50) <= tolerance
                or abs(lo[t] - fib618) <= tolerance
            )

    return support, candles


def raw_signals(df, ctx, k):
    columns = ["t", "side", "anchor", "A", "opp"]
    n = len(df)
    if n == 0:
        return pd.DataFrame(columns=columns)
    o, h, l, c = (df[x].to_numpy(float) for x in ("open", "high", "low", "close"))
    if not all(np.isfinite(x).all() for x in (o, h, l, c)):
        raise ValueError("OHLC must contain only finite prices")
    a = np.asarray(ctx["atr"], float)
    if a.ndim != 1 or len(a) != n:
        raise ValueError("ctx['atr'] must align with df")
    if k["bb_bars"] == 20:
        lower, upper = np.asarray(ctx["bbl"], float), np.asarray(ctx["bbu"], float)
    else:
        bb = bollinger(df.close, k["bb_bars"])
        lower, upper = bb.lower.to_numpy(float), bb.upper.to_numpy(float)
    stochastic = (np.asarray(ctx["stk"], float) if (k["stoch_bars"], k["stoch_smooth"]) == (14, 3)
                  else stoch_k(df, k["stoch_bars"], k["stoch_smooth"]).to_numpy(float))
    sma = (np.asarray(ctx["sma"][50], float) if k["support_ma"] == 50
           else df.close.rolling(k["support_ma"]).mean().to_numpy(float))
    feature_names = ("strength", "pivot_bars", "ma_tol", "ma_look", "ma_count", "horizontal_gap",
                     "horizontal_count_min", "double_gap", "double_age", "double_tol", "fib_impulse",
                     "fib_age", "fib_a", "fib_b", "pin_ratio", "top_fraction", "body_min")
    support_parts, candle_parts = _features(o, h, l, c, a, sma, *(k[x] for x in feature_names))
    middle = (upper + lower) / 2.0
    sd = (upper - lower) / 4.0
    bands_valid = np.isfinite(lower) & np.isfinite(upper) & (sd >= 0.0)
    band = lower if k["bb_sd"] == 2 else middle - k["bb_sd"] * sd
    bb = bands_valid & (l < band)
    oversold = np.isfinite(stochastic) & (stochastic < k["stoch_max"])
    votes = bb.astype(np.int64) + oversold.astype(np.int64) + support_parts.any(axis=1).astype(np.int64)
    qualified = votes >= 2 if k["required"] == "2" else votes == 3
    if k["required"] == "3+candle":
        qualified &= candle_parts.any(axis=1)
    # Every raw qualification resets suppression, including invalid-ATR bars.
    starts = np.zeros(n, bool)
    last = -k["gap"] - 1
    for u in np.flatnonzero(qualified):
        starts[u] = u - last > k["gap"]
        last = u
    atr_valid = np.isfinite(a) & (a > 0.0)
    eligible = starts & atr_valid
    t = np.flatnonzero(eligible[:-1] & (h[1:] > h[:-1]) & atr_valid[1:]) + 1
    # Confirmation is known at t close, anchor stays at setup bar t-1 low.
    return pd.DataFrame(dict(t=t, side=SIDE, anchor=l[t-1], A=a[t],
                             opp=np.where(bands_valid[t], middle[t], np.nan)), columns=columns)


def signals(raw, k):
    return raw


def lines(df, ctx, k):
    return {}


def exit_recipe(k):
    recipe = dict(EXIT_PANEL[k["exit"]], max_hold=k["max_hold"])
    for field in ("target_R", "half_R", "trail_atr", "time_bars"):
        if field in recipe:
            recipe[field] = k[field]
    return recipe
