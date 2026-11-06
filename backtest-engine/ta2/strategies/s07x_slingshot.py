"""S07X: S07 slingshot (Booming Bulls) signals crossed with the v1 exit panel. TIER: WEAK. Signal code from v1."""


import numpy as np
from .common import EXIT_PANEL, panel_lines, select_signals, panel_named, exit_ladder
import pandas as pd
from numba import njit

from ..indicators import no_earn


FLAGS = [
    "sd2", "sd25", "st10", "st20", "st30",
    "bb", "oversold", "support",
    "supma", "suphorizontal", "supdouble", "supfib",
    "req2", "req3", "req3c",
    "pin", "engulf", "full", "candle",
    "cross20", "trend200", "trend50150", "noearn",
]

# junior's choice: preceding five raw qualifying bars suppress a setup.
_EPISODE_WINDOW = 5


def _base_specs():
    return [
        (
            {
                "bb_sd": deviation,
                "stoch": threshold,
                "trend": trend,
                "required": required,
                "trigger": entry,
            },
            family,
            (sd_flag, f"st{threshold}", required_flag)
            + (() if trend_flag is None else (trend_flag,)),
        )
        for deviation, sd_flag in ((2, "sd2"), (2.5, "sd25"))
        for threshold in (10, 20, 30)
        for trend, trend_flag in (
            ("none", None),
            ("close>SMA200", "trend200"),
            ("SMA50>SMA150", "trend50150"),
        )
        for required, required_flag in (
            ("2 of 3", "req2"),
            ("3 of 3", "req3"),
            ("3 of 3 + candle", "req3c"),
        )
        for entry, family in (
            ("next-day stop above high", "confirm"),
            ("buy the close", "close"),
        )
    ]


# junior's choice: named recipes use BB 2 SD, threshold 20, and the
# listed engine mode/buffer. Additional filters belong in LADDER.
_BASE_NAMED = {
    "as taught (all 4: BB, stoch<20, support, candle; buy-stop above high; 2R)": {
        "fam": "confirm",
        "flags": ("sd2", "st20", "req3c"),
        "target": "2R",
        "mode": 1,
        "buf": 0.1,
    },
    "as traded (2 of 3, buy the close, 2R)": {
        "fam": "close",
        "flags": ("sd2", "st20", "req2"),
        "target": "2R",
        "mode": 0,
        "buf": 0.1,
    },
    "uptrend version (close>SMA200)": {
        "fam": "close",
        "flags": ("sd2", "st20", "req2", "trend200"),
        "target": "2R",
        "mode": 0,
        "buf": 0.1,
    },
}

_BASE_LADDER = {
    "base": {
        "fam": "close",
        "flags": ("sd2", "st20", "req2"),
        "target": "2R",
        "mode": 0,
        "buf": 0.1,
    },
    "steps": [
        ("base (2 of 3 control)", {}, True),
        ("+ lower-band pierce", {"add": "bb"}, True),
        ("+ stochastic < 20", {"add": "oversold"}, True),
        ("+ strong support", {"add": "support"}, True),
        ("+ bullish candle", {"add": "candle"}, True),
        ("+ next-day high confirmation", {"fam": "confirm"}, True),
        ("+ stochastic recovery above 20", {"fam": "cross20"}, True),
        ("+ close > SMA200", {"add": "trend200"}, True),
        ("+ no earnings", {"add": "noearn"}, True),
    ],
}


@njit(cache=True)
def _features(op, hi, lo, cl, atr, sma50):
    """Causal support/candle features in the long orientation."""
    n = len(cl)

    # junior's choice: support pivots use strength 5.
    strength = 5
    pivots = np.empty(252 + 1, dtype=np.int64)
    pivot_count = 0

    # junior's choice: internal column order.
    # Support: MA, horizontal, double-bottom, Fibonacci.
    support = np.zeros((n, 4), dtype=np.bool_)
    # Candles: pin, engulfing, full body.
    candles = np.zeros((n, 3), dtype=np.bool_)
    swing = np.empty(n)
    ma_touch = np.zeros(n, dtype=np.bool_)
    episode_prefix = np.zeros(n + 1, dtype=np.int64)

    for t in range(n):
        valid_atr = np.isfinite(atr[t]) and atr[t] > 0.0

        # junior's choice: MA proximity is 0.5 ATR and a touch must close
        # at or above SMA50. Consecutive touch bars form one episode.
        if valid_atr and np.isfinite(sma50[t]):
            ma_touch[t] = (
                abs(lo[t] - sma50[t]) <= 0.5 * atr[t]
                and cl[t] >= sma50[t]
            )
        starts_episode = ma_touch[t] and (
            t == 0 or not ma_touch[t - 1]
        )
        episode_prefix[t + 1] = (
            episode_prefix[t] + int(starts_episode)
        )

        # junior's choice: swing stop is the trailing 10-bar minimum;
        # startup bars use the available history.
        bottom = lo[t]
        for b in range(max(0, t - 10 + 1), t):
            bottom = min(bottom, lo[b])
        swing[t] = bottom

        body = cl[t] - op[t]
        candle_range = hi[t] - lo[t]
        top_third = (
            candle_range > 0.0
            and cl[t] >= hi[t] - candle_range / 3.0
        )

        # junior's choice: green pin, wick/body >= 2, top-third close.
        candles[t, 0] = (
            body > 0.0
            and op[t] - lo[t] >= 2.0 * body
            and top_third
        )
        candles[t, 1] = (
            t > 0
            and cl[t - 1] < op[t - 1]
            and body > 0.0
            and op[t] <= cl[t - 1]
            and cl[t] >= op[t - 1]
        )
        # junior's choice: full-body cutoff is 60%, with top-third close.
        candles[t, 2] = (
            body > 0.0
            and body >= 0.6 * candle_range
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
            if t - j <= 252:
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
                # junior's choice: each confirmed high replaces the Fib
                # leg; pair with the latest previously confirmed low.
                fib_active = False
                if last_low_j >= 0 and last_low_j < q:
                    height = hi[q] - last_low
                    denominator = abs(last_low)
                    # junior's choice: minimum Fib impulse is 5%.
                    if (
                        denominator > 0.0
                        and height > 0.0
                        and height / denominator >= 0.05
                    ):
                        fib_active = True
                        fib_p = q
                        fib_low = last_low
                        fib_high = hi[q]
                        for b in range(q + 1, t + 1):
                            if lo[b] <= fib_low or hi[b] > fib_high:
                                fib_active = False
                                break

            # Process a simultaneous low after pairing the high.
            if is_low:
                pivots[pivot_count] = q
                pivot_count += 1
                last_low_j = q
                last_low = lo[q]

        if fib_active:
            # junior's choice: expire Fib legs after 252 bars, on loss
            # of the start, or on an excursion above the impulse high.
            if (
                t - fib_p > 252
                or lo[t] <= fib_low
                or hi[t] > fib_high
            ):
                fib_active = False

        if not np.isfinite(atr[t]) or atr[t] <= 0.0:
            continue

        tolerance = 0.5 * atr[t]

        # junior's choice: tested MA requires two prior touch-episode
        # starts in a complete 50-bar window, excluding today.
        if t >= 50 and ma_touch[t]:
            prior_episodes = (
                episode_prefix[t] - episode_prefix[t - 50]
            )
            support[t, 0] = prior_episodes >= 2

        horizontal_count = 0
        newest_selected = -1

        for i in range(pivot_count - 1, -1, -1):
            j = pivots[i]

            # junior's choice: horizontal support needs three known lows
            # near today's low, greedily separated by at least 10 bars.
            if abs(lo[t] - lo[j]) <= tolerance:
                if newest_selected < 0 or newest_selected - j >= 10:
                    horizontal_count += 1
                    newest_selected = j

            # junior's choice: today's low is the second bottom; require
            # spacing 10..120 and equality within 2% of the first low.
            age = t - j
            denominator = abs(lo[j])
            if (
                age >= 10
                and age <= 120
                and denominator > 0.0
                and abs(lo[t] - lo[j]) / denominator <= 0.02
            ):
                support[t, 2] = True

        support[t, 1] = horizontal_count >= 3

        if fib_active:
            height = fib_high - fib_low
            fib50 = fib_high - 0.5 * height
            fib618 = fib_high - 0.618 * height
            support[t, 3] = (
                abs(lo[t] - fib50) <= tolerance
                or abs(lo[t] - fib618) <= tolerance
            )

    return support, candles, swing


@njit(cache=True)
def _episode_starts(qualified):
    """True only when no raw qualifying bar occurred in the prior window."""
    n = len(qualified)
    starts = np.zeros(n, dtype=np.bool_)
    last_qualified = -_EPISODE_WINDOW - 1

    for u in range(n):
        if qualified[u]:
            starts[u] = u - last_qualified > _EPISODE_WINDOW
            # Update on EVERY raw qualification, not just episode starts.
            last_qualified = u

    return starts


@njit(cache=True)
def _events(eligible, hi, stochastic):
    """Build families only from episode-start setups."""
    n = len(eligible)

    # junior's choice: internal family codes:
    # 0 = close, 1 = confirm, 2 = cross20.
    events = np.empty((3 * n, 3), dtype=np.int64)
    count = 0
    consumed = np.zeros(n, dtype=np.bool_)

    for t in range(n):
        if eligible[t]:
            events[count, 0] = t
            events[count, 1] = t
            events[count, 2] = 0
            count += 1

        if t > 0 and eligible[t - 1] and hi[t] > hi[t - 1]:
            events[count, 0] = t
            events[count, 1] = t - 1
            events[count, 2] = 1
            count += 1

        crosses = (
            t > 0
            and np.isfinite(stochastic[t - 1])
            and np.isfinite(stochastic[t])
            and stochastic[t - 1] <= 20.0
            and stochastic[t] > 20.0
        )
        if crosses:
            selected = -1
            # junior's choice: recovery window is the next five bars.
            for u in range(t - 1, max(-1, t - 5 - 1), -1):
                if eligible[u] and not consumed[u]:
                    consumed[u] = True
                    if selected < 0:
                        selected = u
            if selected >= 0:
                events[count, 0] = t
                events[count, 1] = selected
                events[count, 2] = 2
                count += 1

    return events[:count]


def _requirement_events(requirements, atr_valid, hi, stochastic):
    """Debounce each requirement independently, then merge identical events.

    Returned requirement flags identify the episode channels that emitted
    each event. A raw requirement being true is insufficient: its own
    episode-start rule must have admitted the underlying setup.
    """
    parts = []
    requirement_ids = []

    for channel, qualified in enumerate(requirements):
        # Suppression examines raw requirement qualifications. An invalid
        # ATR does not erase a preceding qualification from the window.
        eligible = np.ascontiguousarray(
            _episode_starts(qualified) & atr_valid
        )
        events = _events(eligible, hi, stochastic)
        if len(events) == 0:
            continue

        events = events[atr_valid[events[:, 0]]]
        if len(events) == 0:
            continue

        parts.append(events)
        requirement_ids.append(
            np.full(len(events), channel, dtype=np.int64)
        )

    if not parts:
        return (
            np.empty((0, 3), dtype=np.int64),
            np.empty((0, len(requirements)), dtype=bool),
        )

    combined = np.concatenate(parts, axis=0)
    channels = np.concatenate(requirement_ids)
    events, inverse = np.unique(
        combined, axis=0, return_inverse=True
    )

    membership = np.zeros((len(events), len(requirements)), dtype=bool)
    membership[inverse, channels] = True
    return events, membership


def _aligned(values, n, name):
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 1 or len(array) != n:
        raise ValueError(f"{name} must be a one-dimensional array of length {n}")
    return np.ascontiguousarray(array)


def _signals(df, ctx):
    """Return episode-filtered long/short slingshot events, or None."""
    n = len(df)
    if n == 0:
        return None

    op = _aligned(df["open"], n, "open")
    hi = _aligned(df["high"], n, "high")
    lo = _aligned(df["low"], n, "low")
    cl = _aligned(df["close"], n, "close")
    atr = _aligned(ctx["atr"], n, 'ctx["atr"]')
    stochastic = _aligned(ctx["stk"], n, 'ctx["stk"]')
    lower = _aligned(ctx["bbl"], n, 'ctx["bbl"]')
    upper = _aligned(ctx["bbu"], n, 'ctx["bbu"]')
    sma50 = _aligned(ctx["sma"][50], n, 'ctx["sma"][50]')
    sma150 = _aligned(ctx["sma"][150], n, 'ctx["sma"][150]')
    sma200 = _aligned(ctx["sma"][200], n, 'ctx["sma"][200]')

    # junior's choice: reject unknown OHLC rather than infer pivots,
    # support touches, or confirmation across missing price bars.
    if not all(np.isfinite(a).all() for a in (op, hi, lo, cl)):
        raise ValueError("OHLC must contain only finite prices")

    middle = (upper + lower) / 2.0
    sd = (upper - lower) / 4.0
    bands_valid = (
        np.isfinite(lower) & np.isfinite(upper) & (sd >= 0.0)
    )
    atr_valid = np.isfinite(atr) & (atr > 0.0)
    family_names = np.array(["close", "confirm", "cross20"])
    swing_family_names = np.array([
        "close_swing", "confirm_swing", "cross20_swing"
    ])
    frames = []

    for side in (1, -1):
        if side == 1:
            view_op, view_hi, view_lo, view_cl = op, hi, lo, cl
            view_stochastic = stochastic
            lower2 = lower
        else:
            view_op, view_hi, view_lo, view_cl = -op, -lo, -hi, -cl
            view_stochastic = 100.0 - stochastic
            lower2 = -upper

        view_middle = side * middle
        support_parts, candle_parts, swing = _features(
            view_op, view_hi, view_lo, view_cl, atr, side * sma50
        )
        support = support_parts.any(axis=1)
        candle = candle_parts.any(axis=1)

        crosses = np.zeros(n, dtype=bool)
        crosses[1:] = (
            np.isfinite(view_stochastic[:-1])
            & np.isfinite(view_stochastic[1:])
            & (view_stochastic[:-1] <= 20.0)
            & (view_stochastic[1:] > 20.0)
        )

        for deviation in (2, 2.5):
            band = (
                lower2 if deviation == 2
                else view_middle - 2.5 * sd
            )
            bb = bands_valid & (view_lo < band)

            for threshold in (10, 20, 30):
                oversold = (
                    np.isfinite(view_stochastic)
                    & (view_stochastic < threshold)
                )
                votes = (
                    bb.astype(np.int64)
                    + oversold.astype(np.int64)
                    + support.astype(np.int64)
                )
                req2 = votes >= 2
                req3 = votes == 3
                req3c = req3 & candle

                events, membership = _requirement_events(
                    (req2, req3, req3c),
                    atr_valid,
                    view_hi,
                    view_stochastic,
                )
                if len(events) == 0:
                    continue

                t = events[:, 0]
                u = events[:, 1]
                kind = events[:, 2]
                size = len(t)

                common = pd.DataFrame({
                    "t": t,
                    "side": np.full(size, side, dtype=np.int64),
                    "A": atr[t],
                    # Middle band is evaluated at the actual signal bar.
                    "opp": np.where(bands_valid[t], middle[t], np.nan),
                    "sd2": np.full(size, deviation == 2, dtype=bool),
                    "sd25": np.full(size, deviation == 2.5, dtype=bool),
                    "st10": np.full(size, threshold == 10, dtype=bool),
                    "st20": np.full(size, threshold == 20, dtype=bool),
                    "st30": np.full(size, threshold == 30, dtype=bool),
                    "bb": bb[u],
                    "oversold": oversold[u],
                    "support": support[u],
                    "supma": support_parts[u, 0],
                    "suphorizontal": support_parts[u, 1],
                    "supdouble": support_parts[u, 2],
                    "supfib": support_parts[u, 3],
                    # Requirement flags select independently debounced
                    # channels, preventing cross-channel leakage.
                    "req2": membership[:, 0],
                    "req3": membership[:, 1],
                    "req3c": membership[:, 2],
                    "pin": candle_parts[u, 0],
                    "engulf": candle_parts[u, 1],
                    "full": candle_parts[u, 2],
                    "candle": candle[u],
                    "cross20": crosses[t],
                    "trend200": view_cl[t] > side * sma200[t],
                    "trend50150": (
                        side * sma50[t] > side * sma150[t]
                    ),
                })

                common["fam"] = family_names[kind]
                common["anchor"] = side * view_lo[u]
                frames.append(common)

                swing_frame = common.copy()
                swing_frame["fam"] = swing_family_names[kind]
                swing_frame["anchor"] = side * swing[u]
                frames.append(swing_frame)

    if not frames:
        return None

    result = pd.concat(frames, ignore_index=True)
    times, inverse = np.unique(
        result["t"].to_numpy(dtype=np.int64), return_inverse=True
    )
    earnings_ok = np.asarray(no_earn(ctx, times, 1, 10), dtype=np.bool_)
    if earnings_ok.shape != times.shape:
        raise ValueError("no_earn must return one boolean per supplied bar")
    result["noearn"] = earnings_ok[inverse]
    result[FLAGS] = result[FLAGS].astype(bool)

    # junior's choice: deterministic ordering of independent dial channels.
    result = result.sort_values(
        ["t", "side", "fam", "sd2", "st10", "st20"],
        kind="stable",
    ).reset_index(drop=True)
    return result[
        ["t", "side", "anchor", "A", "opp", "fam"] + FLAGS
    ]


# ------------------------------------------------------------ v2 adapter
OUT = "S07X"
CHUNK = 20
SIDES = (1, -1)
MODES = [0, 1]
BUFS = [0.1, 0.5]
TIER = "weak"
EVIDENCE = ("IS pick 3 (confirm sd2.5 / stoch30, 2 of 3, next-day buy stop, 2R, close entry): TSX IS +21 (.000), OOS +15 (.063), US IS +27 (.005), US OOS +30 (.024). TSX OOS borderline. Trailing-stop versions fail US.")
EXITS = dict(EXIT_PANEL)
TARGETS = list(EXITS)

def specs():
    result = [(dict(setup=f"confirm_sd{sd}_st{st}", bb_sd=sd, stoch=st, required="2 of 3", trigger="next-day stop above high"),
               "confirm", ("sd25" if sd == 2.5 else "sd2", f"st{st}", "req2")) for sd in (2, 2.5) for st in (20, 30)]
    for name, recipe in _BASE_NAMED.items():
        if name.startswith(("as taught", "as traded")):
            result.append((dict(setup=name.split(" (")[0]), recipe["fam"], recipe["flags"]))
    return result
LADDER = exit_ladder(dict(fam="confirm", flags=("sd25", "st30", "req2"), mode=1, buf=0.1))


def signals(df, ctx):
    return select_signals(_signals(df, ctx), specs(), SIDES)


def lines(df, ctx, fam, side):
    return panel_lines(df)


NAMED = {name: dict(recipe, sides=SIDES) for name, recipe in panel_named(_BASE_NAMED).items()}
KEEP = {
    "IS pick 3: slingshot confirm (BB 2.5sd, stoch 30, 2 of 3), 2R": dict(fam="confirm", flags=("sd25", "st30", "req2"), target="2R", mode=0, buf=0.1, sides=(1,)),
    "IS pick 1: same setup, half at 1R + 2-ATR trail": dict(fam="confirm", flags=("sd25", "st30", "req2"), target="half1R_trail2atr", mode=0, buf=0.1, sides=(1,)),
}
KEEP = {k: (v if v is not None else NAMED[k]) for k, v in KEEP.items()}
LIVE = "IS pick 3: slingshot confirm (BB 2.5sd, stoch 30, 2 of 3), 2R"
