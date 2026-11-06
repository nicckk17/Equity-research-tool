"""The one trade simulator (v2). Replaces v1's engine.py, exits.py and the private copies inside S53/S55/S56/S54.

A strategy hands over a SIGNAL TABLE (one row per setup: bar t, side, stop anchor, ATR at signal, optional
opposite target, family, filter flags) plus an EXIT RECIPE. This module turns every signal into a trade,
and every trade into 5 random "twins" (same stock, side, window, stop width in ATR, same exit) so we can
tell skill from market drift.

Exit recipe keys (all optional; combine freely):
  target_R=2.0            fixed target at entry + 2R
  target="opp"            the signal's own price target (column `opp`); twins use the same R multiple
  target=("hi", "lo")     per-bar price lines (long uses the 1st, short the 2nd), e.g. monthly pivots
  state="hist"            exit at the NEXT OPEN after a close where side*line < 0 (indicator / MA exits)
  state_skip_first=True   ...but not on the first bar after entry
  close_line="sma20"      exit AT THE CLOSE when the close is beyond the line (after the entry bar)
  trail_atr=2.0           chandelier stop: best price since entry - 2 x ATR(signal bar); never loosens
  be_R=1.0                move the stop to entry once price has gone +1R (applies from the next bar)
  half_R=1.0              book half at +1R, the rest runs (R = average of the two halves)
  time_bars=10            exit at the close 10 bars after entry
  same_day=True           exit at the close of the entry bar (day trade; with mode 2 = open -> close)
  max_hold=60             hard time limit in bars (default config.MAX_HOLD)

Fill rules (identical to v1): entry at the signal close (mode 0) or next open (mode 1). Added 2026-11-03:
mode 2 = entry at the OPEN of the signal bar t (the signal may use bar t's open and earlier bars only - the
strategy file is responsible; used for gap plays). The entry bar itself can then stop out / hit target.
mode 3 = entry at an ORDER PRICE on bar t (column `px`: a buy-stop / sell-stop / limit that bar t's range shows
would have filled; the stop anchor must not use bar t's high/low). Twins of mode 3 enter at a random bar's open. Per bar, in order:
gap through stop -> fill at open; state exit -> fill at open; stop touched -> fill at stop; gap through target ->
open; target touched -> target; (stop and target in the same bar = stop). Costs per side on every leg,
+0.10% slippage on stop fills, 0.5%/yr borrow on shorts. Reason codes: 0 stop, 1 gap stop, 2 target,
3 gap target, 4 time, 5 rule exit.
"""
from __future__ import annotations
import numpy as np, pandas as pd
from numba import njit
from . import config as C

REASONS = ("stop", "gap_stop", "target", "gap_target", "time", "rule")
COLUMNS = ["entry", "stop", "R", "exit_px", "tgt_mult", "gR", "kC", "kS", "kB", "rgR", "rkC", "rkS", "rkB", "nrand"]
NAN = np.nan


@njit(cache=True)
def _sim(o, h, l, c, days, t, mode, side, stop, risk, eatr, tkind, target,
         state, use_state, skip_first, cline, use_cline, trail, be, half, tbars, maxhold, ent):
    """Returns exit bar, weighted exit price, final reason, stop-fill notional, weighted held days."""
    n = len(o)
    e = t + 1 if mode == 1 else t
    entry = c[t] if mode == 0 else (o[t + 1] if mode == 1 else (o[t] if mode == 2 else ent))
    j0 = t if mode >= 2 else t + 1
    end = min(n, j0 + maxhold)
    if tbars > 0:
        end = min(end, e + tbars + 1)
    elif tbars == -1:
        end = min(end, e + 1)
    best = side * entry
    remaining = 1.0; fills = 0.0; stop_fills = 0.0; held = 0.0; half_done = False
    for j in range(j0, end):
        gap = j > j0 or mode == 0
        rs = -1; px = 0.0
        if gap and side * (o[j] - stop) <= 0.0:
            px = o[j]; rs = 1
        elif use_state and (j > j0 or not skip_first) and side * state[j - 1] < 0.0:
            px = o[j]; rs = 5
        elif (l[j] <= stop) if side == 1 else (h[j] >= stop):
            px = stop; rs = 0
        if rs < 0 and tkind > 0:
            if gap and side * (o[j] - target) >= 0.0:
                px = o[j]; rs = 3
            elif (h[j] >= target) if side == 1 else (l[j] <= target):
                px = target; rs = 2
        if rs < 0 and half > 0.0 and not half_done:
            ht = entry + side * half * risk
            hp = 0.0; hit = False
            if gap and side * (o[j] - ht) >= 0.0:
                hp = o[j]; hit = True
            elif (h[j] >= ht) if side == 1 else (l[j] <= ht):
                hp = ht; hit = True
            if hit:
                fills += 0.5 * hp; held += 0.5 * (days[j] - days[e]); remaining = 0.5; half_done = True
        if rs < 0 and use_cline and j > e and np.isfinite(cline[j]) and side * (c[j] - cline[j]) < 0.0:
            px = c[j]; rs = 5
        if rs < 0 and j == end - 1:
            px = c[j]; rs = 4
        if rs >= 0:
            fills += remaining * px
            held += remaining * (days[j] - days[e])
            if rs <= 1:
                stop_fills += remaining * px
            return j, fills, rs, stop_fills, held
        fav = h[j] if side == 1 else -l[j]
        if be > 0.0 and fav >= side * entry + be * risk:
            stop = side * max(side * stop, side * entry)
        if trail > 0.0:
            best = max(best, fav)
            stop = side * max(side * stop, best - trail * eatr)
    return -1, NAN, -1, NAN, NAN


@njit(cache=True)
def _batch(o, h, l, c, a, days, times, sides, anchors, sig_atr, opp, epx, lo_arr, hi_arr,
           tlong, tshort, state, cline, mode, buf, tkind, tmult, use_state, skip_first, use_cline,
           trail, be, half, tbars, maxhold, min_r, n_twins, warmup, seed):
    np.random.seed(seed)
    m = len(times); n = len(o)
    oi = np.full((m, 4), -1, np.int64)
    of = np.full((m, 14), NAN)
    for s in range(m):
        t = times[s]; side = sides[s]; A = sig_atr[s]
        if t < 0 or t + 1 >= n or not np.isfinite(A) or A <= 0.0:
            continue
        entry = c[t] if mode == 0 else (o[t + 1] if mode == 1 else (o[t] if mode == 2 else epx[s]))
        if not np.isfinite(entry):
            continue
        stop = anchors[s] - side * buf * A
        risk = side * (entry - stop)
        if not np.isfinite(risk) or risk <= 0.0 or risk < min_r * A:
            continue
        if trail > 0.0 and not (np.isfinite(a[t]) and a[t] > 0.0):
            continue
        target = NAN; tm = NAN
        if tkind == 1:
            target = entry + side * tmult * risk
        elif tkind == 2:
            target = opp[s]
        elif tkind == 3:
            target = tlong[t] if side == 1 else tshort[t]
        if tkind >= 2 and not (np.isfinite(target) and side * (target - entry) > 0.0):
            continue
        if tkind > 0:
            tm = side * (target - entry) / risk
        xb, xp, rs, sf, hd = _sim(o, h, l, c, days, t, mode, side, stop, risk, a[t], tkind, target,
                                  state, use_state, skip_first, cline, use_cline, trail, be, half, tbars, maxhold, entry)
        if xb < 0:
            continue
        e = t + 1 if mode == 1 else t
        oi[s, 0] = 1; oi[s, 1] = e; oi[s, 2] = xb; oi[s, 3] = rs
        of[s, 0] = entry; of[s, 1] = stop; of[s, 2] = risk; of[s, 3] = xp; of[s, 4] = tm
        of[s, 5] = side * (xp - entry) / risk
        of[s, 6] = (entry + xp) / risk
        of[s, 7] = sf / risk
        of[s, 8] = entry * hd / (365.0 * risk) if side == -1 else 0.0
        of[s, 13] = 0
        # ---- random twins
        tmode = 2 if mode == 3 else mode   # twins of an order-price entry enter at a random bar's open
        lo = max(lo_arr[s], warmup); hi = min(hi_arr[s], n - 2)
        if hi <= lo:
            continue
        cand = np.empty(hi - lo, np.int64); k = 0
        for er in range(lo, hi):
            if not (np.isfinite(a[er]) and a[er] > 0.0):
                continue
            if use_state and not np.isfinite(state[er]):
                continue
            if tkind == 3:
                e2 = c[er] if tmode == 0 else (o[er + 1] if tmode == 1 else o[er])
                tg = tlong[er] if side == 1 else tshort[er]
                if not (np.isfinite(tg) and side * (tg - e2) > 0.0):
                    continue
            cand[k] = er; k += 1
        if k == 0:
            continue
        acc = np.zeros(4)
        for _ in range(n_twins):
            er = cand[np.random.randint(0, k)]
            e2 = c[er] if tmode == 0 else (o[er + 1] if tmode == 1 else o[er])
            r2 = risk / A * a[er]
            tg2 = NAN
            if tkind == 1 or tkind == 2:
                tg2 = e2 + side * tm * r2
            elif tkind == 3:
                tg2 = tlong[er] if side == 1 else tshort[er]
            xb2, xp2, rs2, sf2, hd2 = _sim(o, h, l, c, days, er, tmode, side, e2 - side * r2, r2, a[er],
                                           1 if tkind == 2 else tkind, tg2, state, use_state, skip_first,
                                           cline, use_cline, trail, be, half, tbars, maxhold, e2)
            acc[0] += side * (xp2 - e2) / r2
            acc[1] += (e2 + xp2) / r2
            acc[2] += sf2 / r2
            acc[3] += e2 * hd2 / (365.0 * r2) if side == -1 else 0.0
        for q in range(4):
            of[s, 9 + q] = acc[q] / n_twins
        of[s, 13] = n_twins
    return oi, of


def _line(lines, key, n):
    if key is None:
        return np.full(n, NAN), False
    v = np.ascontiguousarray(lines[key], dtype=np.float64)
    if len(v) != n:
        raise ValueError(f"line {key!r} has {len(v)} values, expected {n}")
    return v, True


def trades(df: pd.DataFrame, ctx: dict, sg: pd.DataFrame, mode: int, buf: float, exit_recipe: dict,
           lines=None, seed: int = 0, max_hold: int | None = None) -> pd.DataFrame:
    """sg: t, side, anchor, A, opp, lo, hi (window bounds for twins). lines: dict of per-bar arrays the
    exit recipe refers to (built by the strategy, may depend on the family). Returns one row per signal."""
    o, h, l, c = (np.ascontiguousarray(df[k], dtype=np.float64) for k in ("open", "high", "low", "close"))
    n = len(o); x = dict(exit_recipe); lines = lines or {}
    days = df.index.values.astype("datetime64[D]").astype(np.int64)
    tg = x.get("target")
    tkind, tmult = 0, 0.0
    tl = ts = np.full(n, NAN)
    if x.get("target_R"):
        tkind, tmult = 1, float(x["target_R"])
    elif tg == "opp":
        tkind = 2
    elif isinstance(tg, (tuple, list)):
        tkind = 3; tl, _ = _line(lines, tg[0], n); ts, _ = _line(lines, tg[1], n)
    state, us = _line(lines, x.get("state"), n)
    cline, uc = _line(lines, x.get("close_line"), n)
    mh = int(x.get("max_hold") or max_hold or C.MAX_HOLD)
    oi, of = _batch(o, h, l, c, np.ascontiguousarray(ctx["atr"], dtype=np.float64), days,
                    sg.t.to_numpy(np.int64), sg.side.to_numpy(np.int64), sg.anchor.to_numpy(np.float64),
                    sg.A.to_numpy(np.float64), sg.opp.to_numpy(np.float64),
                    (sg.px.to_numpy(np.float64) if "px" in sg else np.full(len(sg), NAN)), sg.lo.to_numpy(np.int64),
                    sg.hi.to_numpy(np.int64), tl, ts, state, cline, int(mode), float(buf), tkind, tmult,
                    us, bool(x.get("state_skip_first", False)), uc, float(x.get("trail_atr", 0) or 0),
                    float(x.get("be_R", 0) or 0), float(x.get("half_R", 0) or 0), (-1 if x.get("same_day") else int(x.get("time_bars", 0) or 0)),
                    mh, C.MIN_R_ATR, C.N_TWINS, C.TWIN_WARMUP, int(seed))
    r = pd.DataFrame(of, columns=COLUMNS, index=sg.index)
    r["valid"] = oi[:, 0] == 1; r["e"] = oi[:, 1]; r["exit_bar"] = oi[:, 2]; r["reason"] = oi[:, 3]
    return r


# ---------------------------------------------------------------- after-cost R, overlap, stats
def r_net(x, cost=C.COST_MAIN):
    """Trade R and twin R after costs at fee level `cost` (x: DataFrame or dict of arrays)."""
    rn = x["gR"] - cost * x["kC"] - C.STOP_SLIP * x["kS"] - C.BORROW * x["kB"]
    rr = x["rgR"] - cost * x["rkC"] - C.STOP_SLIP * x["rkS"] - C.BORROW * x["rkB"]
    return np.asarray(rn, float), np.asarray(rr, float)


@njit(cache=True)
def nonoverlap(sym_code, e, xb):
    """One open position per stock at a time. Input sorted by stock, then entry bar."""
    keep = np.zeros(len(e), np.bool_)
    last = -1; prev = -1
    for i in range(len(e)):
        if sym_code[i] != prev:
            prev = sym_code[i]; last = -1
        if e[i] > last:
            keep[i] = True; last = xb[i]
    return keep


def stats(rn, rr, dates) -> dict:
    if len(rn) == 0:
        return dict(n=0)
    g, ls = rn[rn > 0].sum(), -rn[rn < 0].sum()
    s = rn[np.argsort(dates, kind="stable")] <= 0; best = cur = 0
    for v in s:
        cur = cur + 1 if v else 0; best = max(best, cur)
    return dict(n=len(rn), win=round((rn > 0).mean() * 100, 1), avgR=round(rn.mean(), 3),
                PF=round(g / ls, 2) if ls > 0 else np.nan, randR=round(float(np.nanmean(rr)), 3),
                edge=round(float(np.nanmean(rn - rr)), 3), lose_streak=int(best))


def block_boot(sums, counts, B=C.BOOT, seed=C.SEED):
    """Week-block bootstrap of the edge (trade R - twin R). sums/counts: configs x weeks.
    Same week draw for every config. Returns mean, se, t, single p (mean<=0) and Romano-Wolf max-t p."""
    rng = np.random.default_rng(seed)
    Cn, W = sums.shape
    tot = counts.sum(1)
    mean = np.where(tot > 0, sums.sum(1) / np.maximum(tot, 1), np.nan)
    boots = np.empty((B, Cn))
    for b in range(B):
        w = np.bincount(rng.integers(0, W, W), minlength=W).astype(float)
        boots[b] = (sums @ w) / np.maximum(counts @ w, 1)
    se = boots.std(0, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        tstat = mean / se
        tcent = (boots - mean) / se
    p_single = ((boots - mean) >= mean).mean(0)
    ok = np.isfinite(tstat)
    maxt = np.nanmax(np.where(ok, tcent, -np.inf), axis=1)
    p_rw = np.array([(maxt >= ts).mean() if np.isfinite(ts) else np.nan for ts in tstat])
    return mean, se, tstat, p_single, p_rw


# ---------------------------------------------------------------- daily mark-to-market portfolio
def portfolio(tr: pd.DataFrame, closes: pd.DataFrame, start, end, cost=C.COST_MAIN, risk=C.RISK_PER_TRADE,
              max_open=C.MAX_OPEN, cap=C.NOTIONAL_CAP, max_gross=C.MAX_GROSS, cash_rate=None,
              order="random", seed=7) -> dict:
    """tr: non-overlapping trades (sym, side, entry_date, exit_date, entry, exit_px, R, reason[, atr_pct]).
    Sizing: risk x equity / R shares, capped at cap x equity, total gross <= max_gross x equity (no margin).
    Same-day candidates: random order (v1) or "low_vol" (lowest ATR/price first, as the live S53 rules).
    cash_rate: optional daily series of annual % (T-bill) earned on idle cash; None = cash earns 0 (v1)."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    cl = closes.loc[start:end]; cal = cl.index
    tr = tr[(tr.entry_date >= cal[0]) & (tr.entry_date <= cal[-1])].copy()
    tr["rk"] = (tr["atr_pct"] if order == "low_vol" and "atr_pct" in tr else
                np.random.default_rng(seed).random(len(tr)))
    by_entry = {d: g.sort_values("rk") for d, g in tr.groupby("entry_date")}
    cr = (cash_rate.reindex(cal, method="ffill").fillna(0) / 100 / 252) if cash_rate is not None else None
    cash = eq_prev = 1.0; pos = []; curve = []; taken = skipped = skipped_cash = 0; nopen = []

    def close_due(pos, d, cash):
        still = []
        for p in pos:
            if p["exit_date"] <= d:
                px = p["exit_px"]; slip = C.STOP_SLIP * px * p["sh"] if p["reason"] <= 1 else 0.0
                cash += p["sh"] * px * (1 - cost) - slip if p["side"] == 1 else -(p["sh"] * px * (1 + cost) + slip)
            else:
                still.append(p)
        return cash, still

    for d in cal:
        row = cl.loc[d]
        if cr is not None and cash > 0:
            cash *= 1 + cr.loc[d]
        cash, pos = close_due(pos, d, cash)
        for r in (by_entry[d].itertuples() if d in by_entry else ()):
            if len(pos) >= max_open:
                skipped += 1; continue
            sh = min(risk * eq_prev / r.R, cap * eq_prev / r.entry)
            room = max_gross * eq_prev - sum(abs(p["sh"] * p["mark"]) for p in pos)
            if room < 0.01 * eq_prev:
                skipped_cash += 1; continue
            sh = min(sh, room / r.entry)
            cash += -sh * r.entry * (1 + cost) if r.side == 1 else sh * r.entry * (1 - cost)
            pos.append(dict(sym=r.sym, side=r.side, sh=sh, exit_date=r.exit_date, exit_px=r.exit_px,
                            reason=r.reason, mark=r.entry)); taken += 1
        cash, pos = close_due(pos, d, cash)
        mv = 0.0
        for p in pos:
            px = row[p["sym"]]; p["mark"] = px
            if p["side"] == -1:
                cash -= p["sh"] * px * C.BORROW / 365.0
            mv += p["side"] * p["sh"] * px
        eq = cash + mv; curve.append(eq); eq_prev = eq; nopen.append(len(pos))
    cs = pd.Series(curve, index=cal); yrs = (cal[-1] - cal[0]).days / 365.25
    ret = cs.pct_change().dropna()
    return dict(taken=taken, skipped_full=skipped, skipped_cash=skipped_cash, end_value=round(cs.iloc[-1], 3),
                cagr=round((cs.iloc[-1] ** (1 / yrs) - 1) * 100, 2), max_dd=round((cs / cs.cummax() - 1).min() * 100, 1),
                sharpe=round(ret.mean() / ret.std() * np.sqrt(252), 2) if ret.std() > 0 else np.nan,
                avg_open=round(float(np.mean(nopen)), 1), max_open_seen=int(max(nopen)), curve=cs)


def buy_hold(series: pd.Series, start, end) -> dict:
    x = series.loc[start:end].dropna()
    yrs = (x.index[-1] - x.index[0]).days / 365.25; v = x / x.iloc[0]; ret = v.pct_change().dropna()
    return dict(end_value=round(v.iloc[-1], 3), cagr=round((v.iloc[-1] ** (1 / yrs) - 1) * 100, 2),
                max_dd=round((v / v.cummax() - 1).min() * 100, 1),
                sharpe=round(ret.mean() / ret.std() * np.sqrt(252), 2), curve=v)
