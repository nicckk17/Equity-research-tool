"""EARN: scheduled pre-earnings momentum. See NOTES for engine/data limitations."""
from __future__ import annotations
import numpy as np
import pandas as pd
from ta3.knobs import Knob

KEY, NAME, SIDE = "EARN", "Pre-earnings trend continuation", 0
TIMEFRAMES, EPISODE_GAP = ["D"], 1
KNOBS = {
    "L": Knob(2, [1, 2, 3, 5], "signal", "Pre-event move in trading sessions"),
    "hold": Knob("E", ["E", "E+1"], "exit", "Exit close of event or following session"),
    "side": Knob("both", ["both", "long_only"], "filter", "Permitted directions"),
    "min_move": Knob(0.0, [0.0, 0.5, 1.0], "filter", "Minimum absolute pre-move in signal ATR"),
    "stop": Knob("2ATR", ["2ATR"], "stop", "none requires engine support; fails explicitly"),
    "mode": Knob(1, [0, 1], "entry", "E-1 close / E open"),
    "buf": Knob(0.0, [0.0], "stop", "Anchor includes two ATR"),
}
SIGNAL_KNOBS = ("L",)

def attach_earnings(df, ctx, earn_dates, calendar=None):
    """Return a copied context with pre-announced event signal dates.

    calendar is a known session-date calendar, never future OHLC. Pass the same
    calendar when testing a price prefix. Dates beyond calendar coverage are ignored.
    Non-session event dates map to the first following session, like context().
    """
    cal = pd.DatetimeIndex(df.index if calendar is None else calendar)
    if not cal.is_unique or not cal.is_monotonic_increasing:
        raise ValueError("calendar must contain unique increasing session dates")
    dates = pd.DatetimeIndex(earn_dates).normalize().dropna().unique().sort_values()
    e = np.unique(cal.searchsorted(dates))
    e = e[(e > 0) & (e < len(cal))]
    out = dict(ctx)
    out["earn_signal_dates"] = cal[e - 1]
    return out

def prepare_earnings(prep):
    """Explicit opt-in preparation before W.run_config or worker dispatch.

    Standard W.Prep does not load earnings. This mutates only the in-memory Prep.
    Use its universe/symbol metadata to load D.earnings, never infer dates from prices.
    """
    from ta2 import data as D
    from ta3 import config as C
    symbols = {s.replace(".TO", ""): s for s in C.UNIVERSES[prep.universe]["symbols"]}
    for it in prep.items:
        sym = symbols[it["sym"]]
        it["ctx"] = attach_earnings(it["df"], it["ctx"], D.earnings(sym, prep.universe))
    prep.cache.clear()
    return prep

def raw_signals(df, ctx, k):
    if "earn_signal_dates" not in ctx:
        raise ValueError("EARN requires attach_earnings() or prepare_earnings(prep); W.Prep has no earnings schedule")
    c = df.close.astype(float)
    move = (c - c.shift(k["L"])).to_numpy(float)
    a = np.asarray(ctx["atr"], float)
    t = df.index.get_indexer(pd.DatetimeIndex(ctx["earn_signal_dates"]))
    t = np.unique(t[t >= 0])
    t = t[np.isfinite(move[t]) & (move[t] != 0) & np.isfinite(a[t]) & (a[t] > 0)]
    side = np.sign(move[t]).astype(int)
    return pd.DataFrame(dict(t=t, side=side, anchor=c.to_numpy()[t] - side * 2 * a[t],
                             A=a[t], opp=np.nan, move_atr=np.abs(move[t]) / a[t]))

def signals(raw, k):
    m = raw.move_atr.ge(k["min_move"])
    if k["side"] == "long_only":
        m &= raw.side.eq(1)
    return raw[m]

def lines(df, ctx, k):
    return {}

def exit_recipe(k):
    if k["stop"] == "none":
        raise NotImplementedError("The unchanged engine requires a finite stop and positive stop-risk R; stop=none is unsupported")
    # Both modes start simulation on E; max_hold counts simulated bars, not signal bars.
    return dict(max_hold=1 if k["hold"] == "E" else 2)
