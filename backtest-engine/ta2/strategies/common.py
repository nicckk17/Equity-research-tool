"""Shared exit recipes and helpers for strategy files (v2)."""
from __future__ import annotations
import numpy as np


def std_exits(names, max_hold=40):
    """v1 shared-engine exits: '1.5R'/'2R'/'3R' fixed targets, 'opp' = the signal's own opposite target."""
    out = {}
    for nm in names:
        out[nm] = dict(target="opp", max_hold=max_hold) if nm == "opp" else dict(target_R=float(nm[:-1]), max_hold=max_hold)
    return out


# v1 exits.py "exit panel" (60-bar hard limit). Same names, so v1 results map 1:1.
EXIT_PANEL = {
    "2R": dict(target_R=2.0, max_hold=60),
    "be1_2R": dict(target_R=2.0, be_R=1.0, max_hold=60),
    "be1_3R": dict(target_R=3.0, be_R=1.0, max_hold=60),
    "trail2atr": dict(trail_atr=2.0, max_hold=60),
    "trail3atr": dict(trail_atr=3.0, max_hold=60),
    "trail_ma20": dict(close_line="sma20", max_hold=60),
    "half1R_trail2atr": dict(half_R=1.0, trail_atr=2.0, max_hold=60),
    "time5": dict(time_bars=5, max_hold=60),
    "time10": dict(time_bars=10, max_hold=60),
}


def panel_lines(df):
    return {"sma20": df.close.rolling(20).mean().to_numpy(float)}


def select_signals(raw, recipes, sides=(1, -1)):
    """Keep only rows used by the given (dials, fam, flags) recipes."""
    if raw is None or raw.empty:
        return raw
    keep = np.zeros(len(raw), dtype=bool)
    for _, fam, flags in recipes:
        keep |= (raw.fam.eq(fam) & raw[list(flags)].all(axis=1)).to_numpy()
    return raw.loc[keep & raw.side.isin(sides)].reset_index(drop=True)


def panel_named(upstream):
    """Cross the original 'as taught' / 'as traded' signal recipes with every panel exit."""
    return {f"{label} | {target}": dict(recipe, target=target)
            for name, recipe in upstream.items()
            for label in ("as taught" if name.startswith("as taught") else "as traded",)
            if name.startswith(("as taught", "as traded"))
            for target in EXIT_PANEL}


def exit_ladder(base):
    return dict(base=dict(base, target="2R"), steps=[(t, {"target": t}, False) for t in EXIT_PANEL])
