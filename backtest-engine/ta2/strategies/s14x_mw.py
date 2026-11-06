"""S14X: S14 M/W double top/bottom signals crossed with the v1 exit panel. TIER: WEAK. Signal code from v1."""


import numpy as np
from .common import EXIT_PANEL, panel_lines, select_signals, panel_named, exit_ladder
import pandas as pd
from numba import njit

from ..indicators import no_earn


FLAGS = [
    "eq1", "eq2", "eq3", "eq5",
    "sp10", "sp20", "tr10", "tr20",
    "power", "vol", "extreme", "room15", "noearn",
]


def _base_specs():
    return [
        (
            {
                "stop": fam,
                "equality": equality,
                "spacing": spacing,
                "trend": trend,
            },
            fam,
            (f"eq{equality}", f"sp{spacing}")
            + (() if trend == "none" else (f"tr{trend}",)),
        )
        for fam in ("top", "leg", "candle")
        for equality in (1, 2, 3, 5)
        for spacing in (10, 20)
        for trend in ("none", 10, 20)
    ]


_BASE_NAMED = {
    "as taught BB/PoS (2nd-leg stop, tops within 3%, prior trend, power candle, 2R, enter at break close)": {
        "fam": "leg",
        "flags": ("eq3", "sp10", "tr10", "power"),
        "target": "2R",
        "mode": 0,
        "buf": 0.1,
    },
    "as traded (pattern-extreme stop, within 3%, pattern-height target, next open)": {
        "fam": "top",
        "flags": ("eq3", "sp10"),
        "target": "opp",
        "mode": 1,
        "buf": 0.1,
    },
    "Murphy (>=20 bars apart, prior trend 20%, volume expands, pattern-height target)": {
        "fam": "top",
        "flags": ("eq3", "sp20", "tr20", "vol"),
        "target": "opp",
        "mode": 1,
        "buf": 0.1,
    },
}

_BASE_LADDER = {
    "base": {
        "fam": "top",
        "flags": ("eq3", "sp10"),
        "target": "2R",
        "mode": 1,
        "buf": 0.1,
    },
    "steps": [
        ("base", {}, True),
        ("+ prior trend >= 10%", {"add": "tr10"}, True),
        ("+ power breakout candle", {"add": "power"}, True),
        ("+ at 52-week extreme", {"add": "extreme"}, True),
        ("+ volume expands", {"add": "vol"}, True),
        ("+ room >= 1.5R", {"add": "room15"}, True),
        ("tops within 1% (alone)", {"add": "eq1"}, False),
        (">= 20 bars apart (alone)", {"add": "sp20"}, False),
        ("+ pattern-height target", {"target": "opp"}, True),
        ("+ no earnings", {"add": "noearn"}, True),
    ],
}


@njit(cache=True)
def _scan_top(hi, lo, cl):
    """Scan the top orientation online; no future bars are inspected."""
    n = len(cl)

    # Inclusive age bound: at most 140 + 1 known pivots.
    slots = 140 + 1
    pairs_per_top = 120 - 10 + 1

    pivots = np.empty(slots, dtype=np.int64)
    pivot_count = 0
    prior_trend = np.full(n, np.nan)

    # Active second tops, grouped by j2. Each group retains every eligible
    # j1 because different necklines can break on different bars.
    second = np.full(slots, -1, dtype=np.int64)
    counts = np.zeros(slots, dtype=np.int64)
    firsts = np.empty((slots, pairs_per_top), dtype=np.int64)
    necks = np.empty((slots, pairs_per_top))
    max_neck = np.full(slots, -np.inf)

    between_low = np.empty(120 + 1)
    between_high = np.empty(120 + 1)

    out_t = np.empty(n, dtype=np.int64)
    out_j1 = np.empty(n, dtype=np.int64)
    out_j2 = np.empty(n, dtype=np.int64)
    out_top = np.empty(n)
    out_opp = np.empty(n)
    out_eq = np.empty(n)
    out_trend = np.empty(n)
    out_leg = np.empty(n)
    out_count = 0

    for t in range(n):
        # Expire known pivots without rescanning historical pivot windows.
        kept = 0
        for i in range(pivot_count):
            j = pivots[i]
            if t - j <= 140:
                pivots[kept] = j
                kept += 1
        pivot_count = kept

        # A strength-5 pivot at j becomes known exactly at j + 5.
        if t >= 5 + 5:
            j = t - 5
            is_pivot = True
            for b in range(j - 5, t + 1):
                if hi[b] > hi[j]:
                    is_pivot = False
                    break
            if is_pivot:
                pivots[pivot_count] = j
                pivot_count += 1

                # junior's choice: require the full 60-bar prior window
                # for trend flags; insufficient history leaves them false.
                if j >= 60:
                    bottom = lo[j - 60]
                    for b in range(j - 60 + 1, j + 1):
                        bottom = min(bottom, lo[b])
                    # junior's choice: absolute denominators preserve
                    # positive percentages under negative-price mirroring.
                    denominator = abs(bottom)
                    if denominator > 0.0:
                        prior_trend[j] = (hi[j] - bottom) / denominator

        best_j2 = -1
        best_j1 = -1
        best_neck = np.nan

        for slot in range(slots):
            j2 = second[slot]
            if j2 < 0:
                continue

            # j1 <= j2 - 10 and t - j1 <= 140 imply this age limit.
            if t - j2 > 140 - 10 or hi[t] > hi[j2]:
                second[slot] = -1
                counts[slot] = 0
                continue

            # No candidate in this group can break at the current close.
            if cl[t] >= max_neck[slot]:
                continue

            kept = 0
            remaining_max = -np.inf
            for i in range(counts[slot]):
                j1 = firsts[slot, i]
                neckline = necks[slot, i]

                if t - j1 > 140:
                    continue

                if cl[t] < neckline:
                    # Remove on its FIRST close below, including j2 + 1.
                    # A break before j2 + 2 never becomes a later signal.
                    if t >= j2 + 2:
                        if (
                            j2 > best_j2
                            or (j2 == best_j2 and j1 > best_j1)
                        ):
                            best_j2 = j2
                            best_j1 = j1
                            best_neck = neckline
                    continue

                firsts[slot, kept] = j1
                necks[slot, kept] = neckline
                remaining_max = max(remaining_max, neckline)
                kept += 1

            counts[slot] = kept
            max_neck[slot] = remaining_max
            if kept == 0:
                second[slot] = -1

        if best_j2 >= 0:
            pattern_top = max(hi[best_j1], hi[best_j2])
            pattern_height = pattern_top - best_neck
            leg = hi[t - 5]
            for b in range(t - 5 + 1, t + 1):
                leg = max(leg, hi[b])

            out_t[out_count] = t
            out_j1[out_count] = best_j1
            out_j2[out_count] = best_j2
            out_top[out_count] = pattern_top
            out_opp[out_count] = best_neck - pattern_height
            out_eq[out_count] = (
                abs(hi[best_j2] - hi[best_j1]) / abs(hi[best_j1])
            )
            out_trend[out_count] = prior_trend[best_j1]
            out_leg[out_count] = leg
            out_count += 1

        # Consider t as a new j2 only AFTER processing older second tops.
        if t < 5 or pivot_count == 0:
            continue

        left_high = True
        for b in range(t - 5, t):
            if hi[b] > hi[t]:
                left_high = False
                break
        if not left_high:
            continue

        # At distance d these arrays exclude both endpoints j1 and j2.
        running_low = np.inf
        running_high = -np.inf
        for d in range(1, min(120, t) + 1):
            between_low[d] = running_low
            between_high[d] = running_high
            running_low = min(running_low, lo[t - d])
            running_high = max(running_high, hi[t - d])

        slot = t % slots
        count = 0
        highest_neck = -np.inf

        for i in range(pivot_count - 1, -1, -1):
            j1 = pivots[i]
            spacing = t - j1
            if spacing < 10 or spacing > 120:
                continue

            denominator = abs(hi[j1])
            if denominator <= 0.0:
                continue
            equality = abs(hi[t] - hi[j1]) / denominator
            if equality > 0.05:
                continue

            pattern_top = max(hi[j1], hi[t])
            if between_high[spacing] > pattern_top:
                continue

            neckline = between_low[spacing]
            if cl[t] < neckline:
                continue

            firsts[slot, count] = j1
            necks[slot, count] = neckline
            highest_neck = max(highest_neck, neckline)
            count += 1

        counts[slot] = count
        max_neck[slot] = highest_neck
        second[slot] = t if count else -1

    return (
        out_t[:out_count],
        out_j1[:out_count],
        out_j2[:out_count],
        out_top[:out_count],
        out_opp[:out_count],
        out_eq[:out_count],
        out_trend[:out_count],
        out_leg[:out_count],
    )


def _aligned(values, n, name):
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 1 or len(array) != n:
        raise ValueError(f"{name} must be a one-dimensional array of length {n}")
    return np.ascontiguousarray(array)


def _signals(df, ctx):
    """Return three stop families per selected pattern, or None."""
    n = len(df)
    if n == 0:
        return None

    op = _aligned(df["open"], n, "open")
    hi = _aligned(df["high"], n, "high")
    lo = _aligned(df["low"], n, "low")
    cl = _aligned(df["close"], n, "close")
    volume = _aligned(df["volume"], n, "volume")
    atr = _aligned(ctx["atr"], n, 'ctx["atr"]')
    vol10 = _aligned(ctx["vol10"], n, 'ctx["vol10"]')
    hi252 = _aligned(ctx["hi252"], n, 'ctx["hi252"]')
    lo252 = _aligned(ctx["lo252"], n, 'ctx["lo252"]')

    # junior's choice: reject missing/nonfinite OHLC rather than infer
    # pivot or first-crossing behavior across unknown price bars.
    if not all(np.isfinite(a).all() for a in (op, hi, lo, cl)):
        raise ValueError("OHLC must contain only finite prices")

    frames = []
    for orientation in (1, -1):
        # Top: real prices, side -1. Bottom: mirrored prices, side +1.
        side = -orientation
        if orientation == 1:
            view_op, view_hi, view_lo, view_cl = op, hi, lo, cl
            ceiling, floor = hi252, lo252
        else:
            view_op, view_hi, view_lo, view_cl = -op, -lo, -hi, -cl
            ceiling, floor = -lo252, -hi252

        scanned = _scan_top(view_hi, view_lo, view_cl)
        t = scanned[0]
        valid_atr = np.isfinite(atr[t]) & (atr[t] > 0.0)
        if not valid_atr.any():
            continue

        t, j1, j2, top, opp, equality, trend, leg = (
            array[valid_atr] for array in scanned
        )
        spacing = j2 - j1
        candle_range = view_hi[t] - view_lo[t]
        body = np.abs(view_cl[t] - view_op[t])

        power = (
            (candle_range > 0.0)
            & (body >= 0.6 * candle_range)
            & (view_cl[t] <= view_lo[t] + candle_range / 3.0)
        )
        extreme = (
            np.isfinite(ceiling[t])
            & (top >= ceiling[t] - atr[t])
        )
        room = (
            np.isfinite(floor[t])
            & (
                (view_cl[t] < floor[t])
                | (
                    view_cl[t] - floor[t]
                    >= 1.5 * (top - view_cl[t])
                )
            )
        )

        common = pd.DataFrame({
            "t": t,
            "side": np.full(len(t), side, dtype=np.int64),
            "A": atr[t],
            "opp": orientation * opp,
            "eq1": equality <= 0.01,
            "eq2": equality <= 0.02,
            "eq3": equality <= 0.03,
            "eq5": equality <= 0.05,
            "sp10": spacing >= 10,
            "sp20": spacing >= 20,
            "tr10": trend >= 0.10,
            "tr20": trend >= 0.20,
            "power": power,
            "vol": (
                np.isfinite(volume[t])
                & np.isfinite(vol10[t])
                & (volume[t] > vol10[t])
            ),
            "extreme": extreme,
            "room15": room,
        })

        for family, anchor in (
            ("top", top),
            ("leg", leg),
            ("candle", view_hi[t]),
        ):
            frame = common.copy()
            frame["fam"] = family
            frame["anchor"] = orientation * anchor
            frames.append(frame)

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

    # junior's choice: deterministic output ordering.
    result = result.sort_values(
        ["t", "side", "fam"], kind="stable"
    ).reset_index(drop=True)
    return result[
        ["t", "side", "anchor", "A", "opp", "fam"] + FLAGS
    ]


# ------------------------------------------------------------ v2 adapter
OUT = "S14X"
CHUNK = 20
SIDES = (1,)
MODES = [0, 1]
BUFS = [0.1, 0.5]
TIER = "weak"
EVIDENCE = ("W-bottom (equality 1%, spacing 10) with SMA20 close exit: IS pick 1 positive in all windows (TSX IS +11, OOS +10, US IS +5, US OOS +8 R/yr; holdout +1) but small and mostly not significant. 'as traded | trail_ma20' similar.")
EXITS = dict(EXIT_PANEL)
TARGETS = list(EXITS)

def specs():
    result = [(dict(setup=f"W_eq1_sp{sp}_{fam}", equality=1, spacing=sp, stop=fam), fam, ("eq1", f"sp{sp}"))
              for sp in (10, 20) for fam in ("top", "leg", "candle")]
    for name, recipe in _BASE_NAMED.items():
        if name.startswith(("as taught", "as traded")):
            result.append((dict(setup=name.split(" (")[0]), recipe["fam"], recipe["flags"]))
    return result
LADDER = exit_ladder(dict(fam="top", flags=("eq1", "sp10"), mode=1, buf=0.1))


def signals(df, ctx):
    return select_signals(_signals(df, ctx), specs(), SIDES)


def lines(df, ctx, fam, side):
    return panel_lines(df)


NAMED = {name: dict(recipe, sides=SIDES) for name, recipe in panel_named(_BASE_NAMED).items()}
KEEP = {
    "IS pick 1: W bottom eq1% sp10, leg stop, SMA20 close exit": dict(fam="leg", flags=("eq1", "sp10"), target="trail_ma20", mode=1, buf=0.1, sides=(1,)),
    "as traded | trail_ma20": None,
}
KEEP = {k: (v if v is not None else NAMED[k]) for k, v in KEEP.items()}
LIVE = "IS pick 1: W bottom eq1% sp10, leg stop, SMA20 close exit"
