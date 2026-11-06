"""One command = the full ta3 pipeline for a strategy on one universe, every timeframe:
sweep (baseline, one-knob-at-a-time, pairs, grid) -> validation (luck correction, plateau, deflated Sharpe,
haircut, per-year, Monte Carlo, walk-forward, real % portfolio vs index) -> graph report (report.html)."""
from __future__ import annotations

import itertools
import json
import time

import numpy as np
import pandas as pd

from . import config as C, quant as Q, report as P, store as S, validate as V
from .knobs import defaults, cid
from .sweep import sweep, strategy


def run(key, universe="TSX", tfs=None, parts=("oat", "pairs", "grid"), workers=None, max_grid=C.MAX_GRID,
        pairs_shown=3, reuse=False):
    t0 = time.time(); mod = strategy(key); knobs = mod.KNOBS
    tfs = tfs or mod.TIMEFRAMES
    bench_sym = C.UNIVERSES[universe]["bench"]; bench = S.load(bench_sym, universe, "D").adj_close
    closes = None; summary = []; sections_tf = []; out_dir = C.RESULTS / f"{key}_{universe}"
    out_dir.mkdir(parents=True, exist_ok=True)
    for tf in tfs:
        try:
            prep, R, T = sweep(key, universe, tf, parts, workers, max_grid=max_grid, reuse=reuse)
        except Exception as ex:                          # e.g. no intraday data stored yet for this universe
            print(f"{tf}: skipped ({ex})"); continue
        if not prep.items:
            print(f"{tf}: no data"); continue
        base = R[R.tags.str.contains("baseline")].iloc[0]; bi = int(base.cfg)
        imp, cur_is = V.knob_impact(R, knobs, "IS"); _, cur_oos = V.knob_impact(R, knobs, "OOS")
        pl, pln = V.plateau(R, knobs, "IS"); R["IS_plateau"] = pl.round(2); R["IS_plateau_n"] = pln
        base = R.loc[R.cfg == bi].iloc[0]
        # best = highest IS edge among configs with enough trades and a plateau >= 0.5 (choose on IS only)
        ok = R[(R.IS_n >= C.MIN_TRADES["IS"]) & (R.IS_plateau >= 0.5)]
        best_i = int(ok.sort_values("IS_edge", ascending=False).cfg.iloc[0]) if len(ok) else bi
        mt = V.multiple_testing(T, R, [bi, best_i], prep)
        F, Swf = V.walk_forward(T, R, knobs, prep, candidates=R[R.tags.str.contains("grid|baseline")].cfg)
        wf = V.wf_summary(F, Swf, knobs)
        tb = T[T.cfg == bi]; py = V.per_year(tb); mc = V.mc_drawdown(tb)
        isr = tb[tb.w == 0].rn.to_numpy()
        siz = dict(kelly=round(Q.kelly_fraction(isr), 3), ruin_033=Q.risk_of_ruin(isr, 0.0033, 0.3, len(isr)),
                   ruin_1pct=Q.risk_of_ruin(isr, 0.01, 0.3, len(isr)))
        port = {}
        if tf not in C.INTRADAY:
            closes = closes if closes is not None else _closes(universe)
            for w in prep.windows:
                port[w] = V.portfolio(tb, prep, closes, w, bench)
        R.to_csv(C.RESULTS / f"{key}_{universe}_{tf}" / "configs.csv", index=False)
        if not F.empty:
            F.to_csv(C.RESULTS / f"{key}_{universe}_{tf}" / "walk_forward.csv", index=False)
        row = dict(tf=tf, symbols=len(prep.items), configs=len(R),
                   **{f"{w}_{m}": base.get(f"{w}_{m}") for w in prep.windows
                      for m in ("n", "avgR", "edge", "p_rw", "sharpeR")},
                   plateau=base.IS_plateau, best=R.loc[R.cfg == best_i, "id"].iloc[0],
                   best_IS_edge=R.loc[R.cfg == best_i, "IS_edge"].iloc[0], best_OOS_edge=R.loc[R.cfg == best_i, "OOS_edge"].iloc[0],
                   dsr_base=_get(mt, bi, "dsr_prob"), haircut_base=_get(mt, bi, "haircut_pct"),
                   wf_oos_edge=wf.get("oos_edge"), wf_p=wf.get("oos_p"), wf_eff=wf.get("efficiency"),
                   wf_pos=wf.get("positive_folds"),
                   **{f"{w}_cagr": port.get(w, {}).get("cagr") for w in ("IS", "OOS")},
                   **{f"{w}_maxdd": port.get(w, {}).get("max_dd") for w in ("IS", "OOS")},
                   **{f"{w}_sharpe": port.get(w, {}).get("sharpe") for w in ("IS", "OOS")},
                   **{f"{w}_sortino": port.get(w, {}).get("sortino") for w in ("IS", "OOS")},
                   **{f"{w}_index_cagr": port.get(w, {}).get("index_cagr") for w in ("IS", "OOS")},
                   **{f"{w}_index_dd": port.get(w, {}).get("index_max_dd") for w in ("IS", "OOS")},
                   mc_dd_p50=mc.get("dd_p50"), mc_dd_p95=mc.get("dd_p95"), kelly=siz["kelly"],
                   ruin30_at_033=siz["ruin_033"], ruin30_at_1pct=siz["ruin_1pct"],
                   badopen_share=base.get("IS_badopen_share"))
        summary.append(row)
        sections_tf.append((tf, prep, R, T, imp, cur_is, cur_oos, pl, mt, F, Swf, wf, py, mc, port, tb))
        print(f"{tf}: done ({time.time() - t0:.0f}s)", flush=True)
    Sm = pd.DataFrame(summary); Sm.to_csv(out_dir / "summary.csv", index=False)
    for standalone, fn in ((True, "report.html"), (False, "report_artifact.html")):
        html = build_report(key, universe, mod, Sm, sections_tf, pairs_shown, standalone)
        (out_dir / fn).write_text(html, encoding="utf-8")
    print(f"report: {out_dir / 'report.html'}  ({time.time() - t0:.0f}s total)")
    return Sm, out_dir / "report.html"


def _get(mt, i, k):
    x = mt[mt.cfg == i]
    return x[k].iloc[0] if len(x) and k in x else None


def _closes(universe):
    m = {}
    for s in C.UNIVERSES[universe]["symbols"]:
        d = S.load(s, universe, "D")
        if len(d):
            m[s.replace(".TO", "")] = d.close
    return pd.concat(m, axis=1).sort_index().ffill()


def build_report(key, universe, mod, Sm, parts, pairs_shown=3, standalone=True):
    knobs = mod.KNOBS
    show = ["tf", "IS_n", "IS_avgR", "IS_edge", "IS_p_rw", "OOS_n", "OOS_avgR", "OOS_edge", "OOS_p_rw", "plateau",
            "dsr_base", "haircut_base", "wf_oos_edge", "wf_p", "wf_pos", "OOS_cagr", "OOS_maxdd", "OOS_sharpe",
            "OOS_sortino", "OOS_index_cagr", "OOS_index_dd", "mc_dd_p95", "kelly", "ruin30_at_033", "ruin30_at_1pct"]
    verdict = Sm[[c for c in show if c in Sm]].copy()
    secs = [("1 Verdict", "Baseline (defaults) per timeframe. edge = R/trade above random entries with the same exit. "
             "p_rw = luck-corrected for every config tried. dsr = deflated Sharpe probability using every config ever "
             "graded. wf = walk-forward (pick on 5 yrs, trade next 1). Portfolio: 0.33% risk/trade, 30 slots, 0.12%/side.",
             P._table(verdict.round(3)) + "<p class='note'>Knobs: " + " ".join(
                 f"<span class='pill'>{k}={v.default}</span>" for k, v in knobs.items()) + "</p>")]
    if len(Sm) > 1:
        secs.append(("2 Timeframes", "Same rules, same defaults, every timeframe.", P._div(P.fig_timeframes(Sm))))
    for (tf, prep, R, T, imp, cur_is, cur_oos, pl, mt, F, Swf, wf, py, mc, port, tb) in parts:
        tag = f" — {tf}"
        secs.append((f"3 Which knob matters{tag}", "Each knob moved alone, every other knob at its default.",
                     P._div(P.fig_tornado(imp)) + P._table(imp)))
        secs.append((f"4 One knob at a time{tag}", "Edge vs random per knob value. Flat lines = robust, a spike = fragile.",
                     P._div(P.fig_oat(cur_is, cur_oos, "edge"))))
        num = [k for k in imp.knob]
        pairs = [(a, b) for a, b in itertools.combinations(num, 2)][:pairs_shown]
        heat = ""
        for a, b in pairs:
            x = R[R.tags.str.contains(f"pair:{a}:{b}|pair:{b}:{a}", regex=True)]
            if len(x) >= 4:
                heat += f"<div class='grid2'>{P._div(P.fig_heat(x, a, b, 'edge', 'IS'))}{P._div(P.fig_heat(x, a, b, 'edge', 'OOS'))}</div>"
        if heat:
            secs.append((f"5 Two knobs together{tag}", "The pairs of the knobs that move the result most. Look for broad warm areas, not one hot cell.", heat))
        secs.append((f"6 Plateau{tag}", f"Baseline plateau score {R.loc[R.tags.str.contains('baseline'), 'IS_plateau'].iloc[0]}. "
                     "1.0 = every neighbour holds 70% of the edge.", P._div(P.fig_plateau(pl))))
        if port and any(port.values()):
            secs.append((f"7 Equity and drawdown{tag}", "Real % portfolio of the baseline vs buy-and-hold of the index.",
                         P._div(P.fig_equity(port))))
        if mc:
            secs.append((f"8 Monte Carlo{tag}", f"Drawdown: actual {mc['dd_hist']}%, median {mc['dd_p50']}%, worst 5% {mc['dd_p95']}%, "
                         f"worst 1% {mc['dd_p99']}%. CAGR range p5..p95: {mc['cagr_p5']}..{mc['cagr_p95']}%.", P._div(P.fig_mc(mc))))
        if len(py):
            secs.append((f"9 Year by year{tag}", "Baseline net R by entry year.", P._div(P.fig_years(py))))
        secs.append((f"10 Trade distribution{tag}", "Net R per trade after costs.", P._div(P.fig_dist(tb))))
        cv = next((p["curve"] for p in port.values() if p), None)
        if cv is not None:
            full = pd.concat([p["curve"] / p["curve"].iloc[0] for p in port.values() if p])
            secs.append((f"11 Monthly returns{tag}", "Portfolio % by month.", P._div(P.fig_monthly(full))))
        if not F.empty:
            secs.append((f"12 Walk-forward{tag}", json.dumps({k: v for k, v in wf.items()}, default=str),
                         P._div(P.fig_wf(Swf)) + P._table(F)))
        if len(mt):
            secs.append((f"Multiple testing{tag}", "Deflated Sharpe and Harvey-Liu haircut for baseline and the IS-best plateau config.",
                         P._table(mt)))
    return P.page(f"{key} {mod.NAME} — {universe}", f"ta3 report, {pd.Timestamp.now():%Y-%m-%d %H:%M}", secs,
                  standalone, name=f"{key} {universe} Knob Report")
