"""Validation: the v1 checks made automatic for every sweep, plus rolling walk-forward.

  knob_impact    one-at-a-time: how much each knob moves the result (range of the metric across its values)
  plateau        share of a config's one-step neighbours keeping >= 70% of its metric (spike vs plateau)
  deflated       Deflated Sharpe (Bailey & Lopez de Prado) using the GLOBAL trial count (v1 + every ta3 sweep)
  haircut        Harvey-Liu style multiple-testing haircut (Bonferroni + BHY) on the Sharpe / t-stat
  per_year       results by calendar year (v1 S53 check)
  mc_drawdown    3-month block bootstrap of the daily R stream -> drawdown range at the live risk per trade
  walk_forward   rolling: choose on 5 years, trade the next 1, roll yearly; stitched out-of-sample result
  portfolio      real % portfolio (ta2 engine: sizing, 30 slots, costs) vs buy-and-hold of the index
The random-twin edge and Romano-Wolf luck correction come from sweep.py (every config, every window).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm, skew, kurtosis

from . import config as C
from .knobs import neighbours, cid
from .sweep import total_trials
from ta2 import engine as E


# ---------------------------------------------------------------- helpers
def daily_R(tr, start=None, end=None):
    """Net R summed by exit day, on a business-day calendar (0 on days with no exits)."""
    if not len(tr):
        return pd.Series(dtype=float)
    s = pd.Series(tr.rn.to_numpy(), index=pd.DatetimeIndex(tr.xd).normalize()).groupby(level=0).sum()
    cal = pd.bdate_range(pd.Timestamp(start or s.index.min()).normalize(), pd.Timestamp(end or s.index.max()).normalize())
    return s.reindex(cal, fill_value=0.0)


def _metric_col(R, w, m=C.SCORE):
    return f"{w}_{m}"


# ---------------------------------------------------------------- knob impact (one at a time)
def knob_impact(R, knobs, w="IS", m=C.SCORE):
    """For each knob: its OAT values and metric, and the swing (max - min). Bigger swing = knob matters more."""
    rows, curves = [], {}
    for k in knobs:
        x = R[R.tags.str.contains(f"oat:{k}(?:;|$)", regex=True) | R.tags.str.contains("baseline")]
        x = x[[all(x_ == d for x_, d in zip([r[kk] for kk in knobs if kk != k], [knobs[kk].default for kk in knobs if kk != k]))
               for _, r in x.iterrows()]]
        x = x.drop_duplicates(k).set_index(k)[[_metric_col(R, w, m), f"{w}_n"]]
        order = [v for v in knobs[k].values if v in x.index]
        x = x.loc[order]; curves[k] = x
        v = x[_metric_col(R, w, m)].astype(float)
        rows.append(dict(knob=k, label=knobs[k].label, part=knobs[k].part, default=knobs[k].default,
                         best=v.idxmax() if v.notna().any() else None, swing=round(float(v.max() - v.min()), 4),
                         at_default=round(float(v.get(knobs[k].default, np.nan)), 4)))
    return pd.DataFrame(rows).sort_values("swing", ascending=False), curves


# ---------------------------------------------------------------- plateau
def plateau(R, knobs, w="IS", m=C.SCORE):
    """Per config: share of its one-step neighbours (that were run) that keep >= PLATEAU_KEEP of its metric.
    Only meaningful for configs with a positive metric."""
    col = _metric_col(R, w, m); val = dict(zip(R.id, R[col].astype(float)))
    out = np.full(len(R), np.nan); cnt = np.zeros(len(R), int)
    for i, r in enumerate(R.itertuples(index=False)):
        cfg = {k: getattr(r, k) for k in knobs}; v = val[r.id]
        if not np.isfinite(v) or v <= 0:
            continue
        nb = [val.get(cid(c)) for c in neighbours(cfg, knobs)]
        nb = [x for x in nb if x is not None and np.isfinite(x)]
        if nb:
            out[i] = np.mean([x >= C.PLATEAU_KEEP * v for x in nb]); cnt[i] = len(nb)
    return pd.Series(out, index=R.index), pd.Series(cnt, index=R.index)


# ---------------------------------------------------------------- deflated Sharpe + haircut
def deflated_sharpe(sr, T, sk, ku, n_trials, sr_var):
    """Probability the true Sharpe > 0 after picking the best of n_trials (per-period Sharpe units)."""
    g = 0.5772156649
    if n_trials < 2 or sr_var <= 0:
        sr0 = 0.0
    else:
        sr0 = np.sqrt(sr_var) * ((1 - g) * norm.ppf(1 - 1 / n_trials) + g * norm.ppf(1 - 1 / (n_trials * np.e)))
    den = np.sqrt(max(1e-12, 1 - sk * sr + (ku - 1) / 4 * sr ** 2))
    return float(norm.cdf((sr - sr0) * np.sqrt(T - 1) / den)), float(sr0)


def haircut(sr_ann, t, n_trials):
    """Harvey-Liu style: adjust the single-test p for n_trials (Bonferroni and BHY), map back to a t and a
    haircut Sharpe. Returns dict with p, p_bonf, p_bhy, t_bhy, sharpe_haircut, haircut_pct."""
    p = float(norm.sf(t)) if np.isfinite(t) else np.nan
    c = float(np.sum(1 / np.arange(1, n_trials + 1)))
    pb = min(1.0, p * n_trials); pbhy = min(1.0, p * n_trials * c / 1)   # BHY for the top-ranked test
    t_bhy = float(norm.isf(pbhy)) if pbhy < 1 else 0.0
    sh = sr_ann * max(0.0, t_bhy) / t if t and np.isfinite(t) and t > 0 else 0.0
    return dict(p=p, p_bonf=pb, p_bhy=pbhy, t=float(t), t_bhy=t_bhy, sharpe_haircut=round(sh, 3),
                haircut_pct=round(100 * (1 - sh / sr_ann), 1) if sr_ann > 0 else np.nan)


def multiple_testing(T, R, ids, prep, n_trials=None):
    """Deflated Sharpe + haircut for chosen configs, on IS+OOS daily R streams."""
    n_trials = n_trials or total_trials()
    a = min(v[0] for v in prep.windows.values()); b = max(v[1] for v in prep.windows.values())
    srs = []
    for i in R.cfg:
        d = daily_R(T[T.cfg == i], a, b)
        srs.append(d.mean() / d.std() if d.std() > 0 else np.nan)
    sr_var = float(np.nanvar(srs)); rows = []
    for cfg_i in ids:
        d = daily_R(T[T.cfg == cfg_i], a, b); n = len(d)
        if n < 30 or d.std() == 0:
            continue
        sr = float(d.mean() / d.std()); t = sr * np.sqrt(n)
        dsr, sr0 = deflated_sharpe(sr, n, float(skew(d)), float(kurtosis(d, fisher=False)), n_trials, sr_var)
        h = haircut(sr * np.sqrt(252), t, n_trials)
        rows.append(dict(cfg=cfg_i, id=R.loc[R.cfg == cfg_i, "id"].iloc[0], sharpeR_ann=round(sr * np.sqrt(252), 3),
                         t=round(t, 2), trials=n_trials, dsr_prob=round(dsr, 4), sr0_ann=round(sr0 * np.sqrt(252), 3),
                         **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in h.items() if k != "t"}))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- per year + Monte Carlo
def per_year(tr):
    if not len(tr):
        return pd.DataFrame()
    y = pd.DatetimeIndex(tr.ed).year
    g = tr.assign(y=y, edge=tr.rn - tr.rr).groupby("y")
    return pd.DataFrame(dict(n=g.size(), avgR=g.rn.mean().round(3), edge=g.edge.mean().round(3),
                             R=g.rn.sum().round(1), win=(g.rn.apply(lambda s: (s > 0).mean() * 100)).round(1)))


def mc_drawdown(tr, risk=C.RISK_PER_TRADE, sims=C.MC_SIMS, block=C.MC_BLOCK_DAYS, seed=C.SEED):
    """Block bootstrap of the daily R stream (3-month blocks keep losing streaks together). Equity compounds at
    `risk` per R. Returns drawdown and final-value percentiles over the same length of history."""
    d = daily_R(tr).to_numpy()
    if len(d) < block * 2:
        return {}
    rng = np.random.default_rng(seed); n = len(d); nb = int(np.ceil(n / block))
    starts = rng.integers(0, n - block, size=(sims, nb))
    paths = np.stack([np.concatenate([d[s:s + block] for s in row])[:n] for row in starts])
    eq = np.cumprod(1 + risk * paths, axis=1)
    dd = (eq / np.maximum.accumulate(eq, axis=1) - 1).min(axis=1)
    yrs = n / 252; cagr = eq[:, -1] ** (1 / yrs) - 1
    hist_eq = np.cumprod(1 + risk * d); hist_dd = float((hist_eq / np.maximum.accumulate(hist_eq) - 1).min())
    return dict(dd_hist=round(hist_dd * 100, 1), dd_p50=round(float(np.percentile(dd, 50)) * 100, 1),
                dd_p95=round(float(np.percentile(dd, 5)) * 100, 1), dd_p99=round(float(np.percentile(dd, 1)) * 100, 1),
                cagr_p5=round(float(np.percentile(cagr, 5)) * 100, 2), cagr_p50=round(float(np.percentile(cagr, 50)) * 100, 2),
                cagr_p95=round(float(np.percentile(cagr, 95)) * 100, 2), prob_loss=round(float((eq[:, -1] < 1).mean()), 3),
                dd_dist=dd)


# ---------------------------------------------------------------- walk-forward
def _folds(prep):
    a = min(v[0] for v in prep.windows.values()); b = max(v[1] for v in prep.windows.values())
    if prep.tf in C.INTRADAY:
        edges = pd.date_range(a, b, periods=C.WF_INTRADAY_FOLDS + 2)
        return [(edges[0], edges[i], edges[i], edges[i + 1]) for i in range(1, len(edges) - 1)]   # anchored
    out = []; y = a.year
    while True:
        tr0 = pd.Timestamp(f"{y}-01-01"); te0 = pd.Timestamp(f"{y + C.WF_TRAIN_YEARS}-01-01")
        te1 = min(pd.Timestamp(f"{y + C.WF_TRAIN_YEARS + C.WF_TEST_YEARS}-01-01"), b)
        if te0 >= b:
            break
        out.append((max(tr0, a), te0, te0, te1)); y += C.WF_TEST_YEARS
    return out


def walk_forward(T, R, knobs, prep, candidates=None, min_trades=50, smooth=True):
    """Each fold: score every candidate on the train years by the t-stat of its edge (trade R - twin R);
    with smooth=True the score is averaged with its one-step neighbours (prefers plateaus over spikes).
    Trade the winner on the next test year. Returns (fold table, stitched OOS trades)."""
    cands = list(candidates if candidates is not None else R.cfg)
    ids = dict(zip(R.cfg, R.id)); by_id = {v: k for k, v in ids.items()}
    nb = {}
    if smooth:
        for i in cands:
            r = R.loc[R.cfg == i].iloc[0]; cfg = {k: r[k] for k in knobs}
            nb[i] = [by_id[cid(c)] for c in neighbours(cfg, knobs) if cid(c) in by_id]
    ed = pd.DatetimeIndex(T.ed); folds = []; picks = []
    for (a, b, c, d) in _folds(prep):
        tr = T[(ed >= a) & (ed < b) & np.isfinite(T.rr)]
        g = tr.assign(e=tr.rn - tr.rr).groupby("cfg").e
        st = pd.DataFrame(dict(n=g.size(), m=g.mean(), s=g.std()))
        st["t"] = st.m / (st.s / np.sqrt(st.n)); st.loc[st.n < min_trades, "t"] = np.nan
        tmap = st.t.to_dict()
        score = {i: (np.nanmean([tmap.get(i, np.nan)] + [tmap.get(j, np.nan) for j in nb.get(i, [])])
                     if smooth else tmap.get(i, np.nan)) for i in cands if np.isfinite(tmap.get(i, np.nan))}
        if not score:
            continue
        best = max(score, key=score.get)
        te = T[(T.cfg == best) & (ed >= c) & (ed < d)]
        trn = tr[tr.cfg == best]
        folds.append(dict(train=f"{a:%Y-%m-%d}..{b:%Y-%m-%d}", test=f"{c:%Y-%m-%d}..{d:%Y-%m-%d}", pick=ids[best],
                          train_n=len(trn), train_edge=round(float((trn.rn - trn.rr).mean()), 4),
                          test_n=len(te), test_avgR=round(float(te.rn.mean()), 4) if len(te) else np.nan,
                          test_edge=round(float((te.rn - te.rr).mean()), 4) if len(te) else np.nan,
                          test_R=round(float(te.rn.sum()), 1)))
        picks.append(te)
    F = pd.DataFrame(folds)
    S = pd.concat(picks, ignore_index=True) if picks else T.iloc[:0]
    return F, S


def wf_summary(F, S, knobs):
    if F.empty:
        return {}
    stab = {}
    for k in knobs:
        vals = F.pick.str.extract(f"(?:^|\\|){k}=([^|]+)")[0]
        stab[k] = round(float(vals.value_counts(normalize=True).iloc[0]), 2)
    S = S[np.isfinite(S.rr)]
    e = (S.rn - S.rr).to_numpy()
    wk = (pd.DatetimeIndex(S.ed).normalize().values.astype("datetime64[D]").astype(np.int64) + 3) // 7
    uw, wi = np.unique(wk, return_inverse=True)
    sums = np.zeros((1, len(uw))); cnt = np.zeros_like(sums)
    np.add.at(sums[0], wi, e); np.add.at(cnt[0], wi, 1)
    p = float(E.block_boot(sums, cnt)[3][0]) if len(S) > 20 else np.nan
    return dict(folds=len(F), oos_trades=len(S), oos_avgR=round(float(S.rn.mean()), 4),
                oos_edge=round(float(e.mean()), 4), oos_p=round(p, 4),
                efficiency=round(float(F.test_edge.mean() / F.train_edge.mean()), 2) if F.train_edge.mean() > 0 else np.nan,
                positive_folds=f"{int((F.test_R > 0).sum())}/{len(F)}",
                pick_stability=stab)


# ---------------------------------------------------------------- real % portfolio
def portfolio(tr, prep, closes, w, bench=None):
    a, b = prep.windows[w]
    x = tr[(tr.w == list(prep.windows).index(w))]
    if not len(x) or prep.tf in C.INTRADAY:
        return {}
    t = pd.DataFrame(dict(sym=x.sym, side=1, entry_date=pd.DatetimeIndex(x.ed).normalize(),
                          exit_date=pd.DatetimeIndex(x.xd).normalize(), entry=x.entry, exit_px=x.exit_px, R=x.R,
                          reason=x.reason, atr_pct=x.atr_pct))
    p = E.portfolio(t, closes, a.normalize(), b.normalize(), order="low_vol")
    out = {k: v for k, v in p.items() if k != "curve"}; out["curve"] = p["curve"]
    ret = p["curve"].pct_change().dropna(); dn = ret[ret < 0]
    out["sortino"] = round(float(ret.mean() / dn.std() * np.sqrt(252)), 2) if len(dn) > 1 else np.nan
    if bench is not None:
        bh = E.buy_hold(bench, a.normalize(), b.normalize())
        out["index_cagr"], out["index_max_dd"], out["index_sharpe"] = bh["cagr"], bh["max_dd"], bh["sharpe"]
        out["index_curve"] = bh["curve"]
    return out
