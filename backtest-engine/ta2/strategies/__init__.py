"""Strategy registry. Only strategies that showed an edge (strong or weak) live here as code.
Every rejected strategy is in docs/REJECTED_LOG.md (what was tested, every variation, results) - check it
before testing a "new" idea, so nothing is re-tested by accident.

A strategy file provides (see _template.py):
  OUT, TIER, EVIDENCE, CHUNK, SIDES, MODES, BUFS, FLAGS, EXITS (name -> exit recipe, see engine.py), TARGETS
  signals(df, ctx) -> table: t, side, anchor, A, opp, fam, + one bool column per FLAG
  lines(df, ctx, fam, side) -> per-bar arrays the exit recipes use (optional)
  specs() -> grid (dials, fam, flags);  NAMED (as taught / as traded);  LADDER;  KEEP (versions with an edge);  LIVE
"""
import importlib

STRATS = {
    "S53": "ta2.strategies.s53_macd",            # strong: MACD histogram cross (the survivor)
    "S55": "ta2.strategies.s55_ema_stack",       # strong: 9/21 EMA cross (passed US cold test)
    "S56": "ta2.strategies.s56_ema55_retest",    # weak: EMA break + retest (best diversifier)
    "S31": "ta2.strategies.s31_rsi_div",         # weak: RSI divergence
    "S54": "ta2.strategies.s54_indicator_stack", # weak: SAR/Force/MACD votes (TSX only)
    "S07X": "ta2.strategies.s07x_slingshot",     # weak: slingshot + 2R
    "S14X": "ta2.strategies.s14x_mw",            # weak: W bottom + SMA20 exit
    "S99": "ta2.strategies.s99_control",
    "HT1": "ta2.strategies.ht1_order_entries",   # weak: Humbled Trader parabolic dip limit buy (only 'para' family kept)         # control: proves the pipeline catches cheats and random entries
}
# Portfolio-type strategies (whole-portfolio rules, own simulators): python -m ta2 portfolio <KEY>
PORTFOLIO = {
    "S45": "ta2.strategies.s45_sector_rotation", # crash protection: same return as XIU, < half the drawdown
    "S43": "ta2.strategies.s43_rs_leaders",      # beats random picks by +4..7%/yr, but below XIU OOS
    "S64": "ta2.strategies.s64_skip_september",  # weak: skip September beat/tied the index in all 4 windows
}


def get(key):
    key = key.upper()
    if key in STRATS:
        return importlib.import_module(STRATS[key])
    if key in PORTFOLIO:
        return importlib.import_module(PORTFOLIO[key])
    raise KeyError(f"{key} is not a kept strategy. Check docs/REJECTED_LOG.md, or add a new file from _template.py")
