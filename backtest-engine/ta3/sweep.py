"""The knob sweep: run every planned config of a strategy on one universe x timeframe, through the ta2 trade
simulator (same fills, costs, slippage, stop-first rule and random-entry twins as v1/v2), and grade each config.

Outputs (results/ta3/<KEY>_<UNIVERSE>_<TF>/):
  configs.csv     one row per config: knob values, tags (baseline / oat:<knob> / pair:<a>:<b> / grid),
                  per window: n, win, avgR, avgR_low, edge, PF, R_yr, sharpeR, p (single), p_rw (Romano-Wolf
                  across ALL configs in this sweep = the luck correction for having tried them all)
  trades.parquet  every trade of every config (for plateau, walk-forward, per-year, Monte Carlo, report)
"""
from __future__ import annotations

import importlib
import multiprocessing as mp
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C, store as S
from .knobs import cid, plan
from ta2 import engine as E
from ta2.indicators import context

_PREP = None      # set before forking workers (shared read-only)


def strategy(key):
    return importlib.import_module(f"ta3.strategies.{key.lower()}")


# ---------------------------------------------------------------- per-universe/timeframe preparation
class Prep:
    def __init__(self, key, universe="TSX", tf="D", holdout=False, only=None):
        self.mod = strategy(key); self.key = key; self.universe = universe; self.tf = tf
        u = C.UNIVERSES[universe]; syms = only or u["symbols"]
        self.items = []
        for code, s in enumerate(syms):
            df = S.load(s, universe, tf, holdout=holdout)
            if len(df) < C.MIN_BARS_TF.get(tf, 300):
                continue
            ctx = context(df)
            self.items.append(dict(code=code, sym=s.replace(".TO", ""), df=df, ctx=ctx,
                                   badopen=S.bad_open_mask(df)))
        self.windows = self._windows(holdout)
        for it in self.items:
            it["win"], it["lo"], it["hi"] = self._bar_windows(it["df"].index)
        self.cache = {}
        # optional strategy hook for extra per-symbol context (e.g. EARN attaches earnings dates)
        hook = getattr(self.mod, "prepare", None) or getattr(self.mod, "prepare_earnings", None)
        if hook:
            hook(self)

    def _windows(self, holdout):
        if self.tf not in C.INTRADAY:
            w = {"IS": C.IS, "OOS": C.OOS}
            if holdout:
                w["HO"] = C.HOLDOUT
            return {k: (pd.Timestamp(a), pd.Timestamp(b) + pd.Timedelta(hours=23, minutes=59)) for k, (a, b) in w.items()}
        lo = min(it["df"].index[0] for it in self.items); hi = max(it["df"].index[-1] for it in self.items)
        cut = lo + (hi - lo) * C.INTRADAY_IS_SHARE
        return {"IS": (lo, cut), "OOS": (cut + pd.Timedelta(seconds=1), hi)}

    def _bar_windows(self, idx):
        win = np.full(len(idx), -1, np.int8); lo = np.zeros(len(idx), np.int64); hi = np.zeros(len(idx), np.int64)
        for j, (a, b) in enumerate(self.windows.values()):
            m = (idx >= a) & (idx <= b)
            win[m] = j; lo[m] = idx.searchsorted(a); hi[m] = idx.searchsorted(b, side="right")
        return win, lo, hi

    def years(self, w):
        a, b = self.windows[w]
        return max((b - a).days / 365.25, 1e-9)


def run_config(prep: Prep, cfg: dict, seed: int = 0) -> pd.DataFrame:
    """All trades of one config across the universe (one open position per stock at a time)."""
    mod = prep.mod; sk = tuple(cfg[k] for k in mod.SIGNAL_KNOBS); out = []
    recipe = mod.exit_recipe(cfg); mode = int(cfg.get("mode", 1)); buf = float(cfg.get("buf", 0.1))
    for it in prep.items:
        ck = (it["code"], sk)
        if ck not in prep.cache:
            raw = mod.raw_signals(it["df"], it["ctx"], cfg)
            prep.cache[ck] = (raw, mod.lines(it["df"], it["ctx"], cfg) if hasattr(mod, "lines") else {})
        raw, lines = prep.cache[ck]
        sg = mod.signals(raw, cfg)
        n = len(it["df"])
        sg = sg[(sg.t >= 1) & (sg.t < n - 1)]
        if not len(sg):
            continue
        t = sg.t.to_numpy(np.int64); w = it["win"][t]; ok = w >= 0
        sg = sg[ok].copy(); t = t[ok]
        if not len(sg):
            continue
        sg["lo"], sg["hi"] = it["lo"][t], it["hi"][t]
        sg = sg.reset_index(drop=True)
        r = E.trades(it["df"], it["ctx"], sg, mode, buf, recipe, lines, seed + it["code"] * 7)
        v = r.valid.to_numpy()
        if not v.any():
            continue
        r = r[v]; e = r.e.to_numpy(np.int64); xb = r.exit_bar.to_numpy(np.int64)
        o = np.argsort(e, kind="stable"); r, e, xb = r.iloc[o], e[o], xb[o]
        keep = E.nonoverlap(np.zeros(len(e), np.int64), e, xb)
        r, e, xb = r[keep], e[keep], xb[keep]
        idx = it["df"].index
        rn, rr = E.r_net(r, C.COST_MAIN); rl, _ = E.r_net(r, C.COST_LOW)
        out.append(pd.DataFrame(dict(
            sym=it["sym"], w=it["win"][sg.t.to_numpy()[r.index.to_numpy()]],
            ed=idx[e].values, xd=idx[xb].values, entry=r.entry.to_numpy(float), exit_px=r.exit_px.to_numpy(float),
            R=r.R.to_numpy(float), reason=r.reason.to_numpy(int), rn=rn, rr=rr, rl=rl,
            atr_pct=sg.A.to_numpy(float)[r.index.to_numpy()] / r.entry.to_numpy(float),
            badopen=it["badopen"][e] & (mode == 1))))
    if not out:
        return pd.DataFrame(columns=["sym", "w", "ed", "xd", "entry", "exit_px", "R", "reason", "rn", "rr", "rl",
                                     "atr_pct", "badopen"])
    return pd.concat(out, ignore_index=True)


def grade(tr: pd.DataFrame, prep: Prep, w: str) -> dict:
    """Trade-level grade for one window (after main costs; edge = trade R - random twin R)."""
    j = list(prep.windows).index(w); x = tr[tr.w == j]
    n = len(x)
    if n == 0:
        return dict(n=0)
    rn, rr = x.rn.to_numpy(), x.rr.to_numpy()
    g, ls = rn[rn > 0].sum(), -rn[rn < 0].sum()
    yrs = prep.years(w)
    day = pd.Series(rn, index=pd.DatetimeIndex(x.xd).normalize()).groupby(level=0).sum()
    a, b = prep.windows[w]
    cal = pd.bdate_range(a.normalize(), min(b, x.xd.max()).normalize())
    daily = day.reindex(cal, fill_value=0.0)
    sr = float(daily.mean() / daily.std() * np.sqrt(252)) if daily.std() > 0 else np.nan
    return dict(n=n, win=round(float((rn > 0).mean() * 100), 1), avgR=round(float(rn.mean()), 4),
                avgR_low=round(float(x.rl.mean()), 4), edge=round(float(np.nanmean(rn - rr)), 4),
                PF=round(float(g / ls), 3) if ls > 0 else np.nan, R_yr=round(float(rn.sum() / yrs), 2),
                edge_yr=round(float(np.nansum(rn - rr) / yrs), 2), sharpeR=round(sr, 3),
                badopen_share=round(float(x.badopen.mean()), 3))


def _init_worker(key, universe, tf, holdout, only):
    global _PREP
    _PREP = Prep(key, universe, tf, holdout, only)


def _worker(args):
    i, cfg = args
    tr = run_config(_PREP, cfg, seed=C.SEED * 1000 + i)
    tr.insert(0, "cfg", i)
    return i, tr


def sweep(key, universe="TSX", tf="D", parts=("oat", "pairs", "grid"), workers=None, holdout=False, only=None,
          max_grid=C.MAX_GRID, quiet=False, reuse=False):
    """reuse=True: load the saved results of an identical earlier sweep instead of re-running it."""
    global _PREP
    t0 = time.time()
    prep = Prep(key, universe, tf, holdout, only); _PREP = prep
    todo = plan(prep.mod.KNOBS, parts, max_grid=max_grid)
    out = C.RESULTS / f"{key}_{universe}_{tf}"; out.mkdir(parents=True, exist_ok=True)
    if reuse and (out / "configs.csv").exists() and (out / "trades.parquet").exists():
        R = pd.read_csv(out / "configs.csv")
        if list(R.id) == [cid(c) for c, _ in todo]:
            if not quiet:
                print(f"{key} {universe} {tf}: reusing saved sweep ({len(R)} configs)")
            return prep, R.drop(columns=[c for c in R if c.startswith("IS_plateau")]), pd.read_parquet(out / "trades.parquet")
    if not quiet:
        print(f"{key} {universe} {tf}: {len(prep.items)} symbols, {len(todo)} configs", flush=True)
    # group configs by signal knobs so each worker reuses its signal cache
    order = sorted(range(len(todo)), key=lambda i: tuple(str(todo[i][0][k]) for k in prep.mod.SIGNAL_KNOBS))
    jobs = [(i, todo[i][0]) for i in order]
    workers = workers or max(1, mp.cpu_count() - 1)
    trades = {}
    if workers > 1 and len(jobs) > 4:
        if "fork" in mp.get_all_start_methods():
            pool = mp.get_context("fork").Pool(workers)
        else:   # Windows: no fork -> each worker rebuilds the same Prep once
            pool = mp.get_context("spawn").Pool(workers, initializer=_init_worker,
                                                initargs=(key, universe, tf, holdout, only))
        with pool:
            for k, (i, tr) in enumerate(pool.imap_unordered(_worker, jobs, chunksize=max(1, len(jobs) // (workers * 8)))):
                trades[i] = tr
                if not quiet and (k + 1) % 50 == 0:
                    print(f"  {k + 1}/{len(jobs)} configs, {time.time() - t0:.0f}s", flush=True)
    else:
        for k, job in enumerate(jobs):
            i, tr = _worker(job); trades[i] = tr
    T = pd.concat([trades[i] for i in range(len(todo))], ignore_index=True)
    # ---- grade + Romano-Wolf across every config of the sweep, per window
    rows = []
    for i, (cfg, tags) in enumerate(todo):
        r = dict(cfg=i, id=cid(cfg), tags=";".join(tags), **cfg)
        tr = T[T.cfg == i]
        for w in prep.windows:
            for m, v in grade(tr, prep, w).items():
                r[f"{w}_{m}"] = v
        rows.append(r)
    R = pd.DataFrame(rows)
    for j, w in enumerate(prep.windows):
        x = T[(T.w == j) & np.isfinite(T.rr)]     # trades whose random twins could be drawn
        if not len(x):
            continue
        wk = (pd.DatetimeIndex(x.ed).normalize().values.astype("datetime64[D]").astype(np.int64) + 3) // 7
        uw, wi = np.unique(wk, return_inverse=True)
        sums = np.zeros((len(todo), len(uw))); cnts = np.zeros_like(sums)
        np.add.at(sums, (x.cfg.to_numpy(), wi), (x.rn - x.rr).to_numpy())
        np.add.at(cnts, (x.cfg.to_numpy(), wi), 1)
        live = cnts.sum(1) >= C.MIN_TRADES.get(w, 50)
        p = np.full(len(todo), np.nan); prw = np.full(len(todo), np.nan)
        if live.sum():
            _, _, _, ps, pr = E.block_boot(sums[live], cnts[live])
            p[live], prw[live] = ps, pr
        R[f"{w}_p"] = np.round(p, 4); R[f"{w}_p_rw"] = np.round(prw, 4)
    R.to_csv(out / "configs.csv", index=False)
    T.to_parquet(out / "trades.parquet")
    _ledger(key, universe, tf, len(todo))
    if not quiet:
        print(f"done: {len(todo)} configs, {len(T):,} trades, {time.time() - t0:.0f}s -> {out}", flush=True)
    return prep, R, T


def _ledger(key, universe, tf, n):
    """Global trial count: every config ever graded (v1 count + every ta3 sweep). Feeds deflated Sharpe."""
    C.LEDGER.parent.mkdir(parents=True, exist_ok=True)
    row = pd.DataFrame([dict(when=pd.Timestamp.now().isoformat(timespec="seconds"), strategy=key, universe=universe,
                             tf=tf, configs=n)])
    row.to_csv(C.LEDGER, mode="a", header=not C.LEDGER.exists(), index=False)


def total_trials():
    n = C.V1_TRIALS
    if C.LEDGER.exists():
        n += int(pd.read_csv(C.LEDGER).configs.sum())
    return n
