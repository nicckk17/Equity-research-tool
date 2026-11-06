"""ta3 self-checks:  python -m ta3.tests.test_ta3   (~1 min). Run after any engine change."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ta3 import config as C, knobs as K, store as S, sweep as W, validate as V
from ta3.strategies import s53


def test_store_weekly_no_lookahead():
    d = S.load("RY.TO", "TSX", "D"); w = S.load("RY.TO", "TSX", "W")
    # every weekly bar is stamped with a day that exists in the daily data and closes at that day's close
    assert w.index.isin(d.index).all()
    assert np.allclose(w.close.values, d.close.reindex(w.index).values)
    # a weekly bar's high never includes a later day
    last = w.index[-5]; prev = w.index[-6]
    assert np.isclose(w.high.loc[last], d.high.loc[(d.index > prev) & (d.index <= last)].max())


def test_plan_dedupes_and_tags():
    p = K.plan(s53.KNOBS, ("oat", "pairs"))
    ids = [K.cid(c) for c, _ in p]
    assert len(ids) == len(set(ids))
    base = [t for c, t in p if "baseline" in t][0]
    assert any(t.startswith("oat:") for t in base)       # the default config is also every knob's default point


def test_neighbours():
    cfg = K.defaults(s53.KNOBS); nb = K.neighbours(cfg, s53.KNOBS)
    assert {"fast": 10} .items() <= {**cfg, "fast": 10}.items()
    assert all(sum(cfg[k] != n[k] for k in cfg) == 1 for n in nb)


def test_parity_with_ta2():
    """ta3 baseline S53 trades == ta2 S53 survivor trades (same signals, fills, costs)."""
    from ta2 import data as D, engine as E
    from ta2.indicators import context
    from ta2.strategies import s53_macd as M
    prep = W.Prep("S53", "TSX", "D", only=["RY.TO", "SU.TO"])
    t3 = W.run_config(prep, K.defaults(s53.KNOBS))
    for s in ("RY.TO", "SU.TO"):
        df = D.load(s, "TSX"); ctx = context(df, D.earnings(s, "TSX"))
        sg = M.signals(df, ctx); sg = sg[(sg.fam == "macd12_26_9") & (sg.side == 1) & sg.zero]
        sg = sg[(sg.t >= 1) & (sg.t < len(df) - 1)].reset_index(drop=True)
        d = df.index[sg.t]; lo = np.zeros(len(sg), np.int64); hi = lo.copy(); keep = np.zeros(len(sg), bool)
        for a, b in (C.IS, C.OOS):
            m = (d >= a) & (d <= b); keep |= m
            lo[m] = df.index.searchsorted(pd.Timestamp(a)); hi[m] = df.index.searchsorted(pd.Timestamp(b), side="right")
        sg["lo"], sg["hi"] = lo, hi; sg = sg[keep].reset_index(drop=True)
        r = E.trades(df, ctx, sg, 1, 0.5, M.EXITS["opposite_cross"], M.lines(df, ctx, "macd12_26_9", 1), 0)
        r = r[r.valid]; k = E.nonoverlap(np.zeros(len(r), np.int64), r.e.to_numpy(), r.exit_bar.to_numpy()); r = r[k]
        x = t3[t3.sym == s.replace(".TO", "")]
        assert len(r) == len(x) and np.allclose(np.sort(E.r_net(r)[0]), np.sort(x.rn.to_numpy()))


def test_deflated_sharpe_sane():
    p1, _ = V.deflated_sharpe(0.1, 2000, 0, 3, 1, 0.001)
    p2, _ = V.deflated_sharpe(0.1, 2000, 0, 3, 100_000, 0.001)
    assert p1 > 0.99 and p2 < p1


def test_haircut_monotone():
    a = V.haircut(1.0, 4.0, 10); b = V.haircut(1.0, 4.0, 100_000)
    assert a["sharpe_haircut"] >= b["sharpe_haircut"]


def test_walk_forward_uses_past_only():
    folds = V._folds(type("P", (), dict(tf="D", windows={"IS": (pd.Timestamp("2000-01-01"), pd.Timestamp("2015-12-31")),
                                                          "OOS": (pd.Timestamp("2016-01-01"), pd.Timestamp("2024-10-31"))}))())
    assert all(b <= c for a, b, c, d in folds) and folds[0][2] == pd.Timestamp("2005-01-01")


def test_quality_flags_bad_tsx_opens():
    q = S.quality(S.load("RY.TO", "TSX", "D", holdout=True))
    assert 2000 in q["bad_open_years"] and 2020 not in q["bad_open_years"]


def test_quant():
    from ta3 import quant as Q
    c = Q.bs_price(100, 100, 1, 0.05, 0.2); p = Q.bs_price(100, 100, 1, 0.05, 0.2, "put")
    assert abs(c - 10.4506) < 1e-3 and abs((c - p) - (100 - 100 * np.exp(-0.05))) < 1e-9     # textbook + put-call parity
    assert abs(Q.implied_vol(c, 100, 100, 1, 0.05) - 0.2) < 1e-6
    g = Q.bs_greeks(100, 100, 1, 0.05, 0.2); assert abs(g["delta"] - 0.6368) < 1e-3
    mc = Q.mc_trade_paths(np.array([-1, -1, 2.5]), n_sims=500); assert mc["dd_p95"] <= mc["dd_p50"] <= 0
    assert Q.max_drawdown([1, 2, 1, 3]) == -0.5 and abs(Q.cagr([1, 1.1], periods=1) - 0.1) < 1e-12
    r = np.random.default_rng(0).normal(0.0005, 0.01, 2000)
    assert abs(Q.sharpe(r) - r.mean() / r.std(ddof=1) * np.sqrt(252)) < 1e-9
    w = Q.vol_target_weight(pd.Series(r)); assert np.isnan(w.iloc[19]) and np.isfinite(w.iloc[20])  # no look-ahead
    gm = Q.garch11(r); assert 0 <= gm["alpha"] + gm["beta"] < 1 and len(gm["cond_vol"]) == len(r)
    rw = np.cumsum(np.random.default_rng(1).normal(0, 1, 5000)) + 1000; assert 0.4 < Q.hurst(np.exp(rw / 100)) < 0.6
    assert Q.block_bootstrap_paths(r, 10, 20).shape == (10, len(r))


def test_orderflow():
    from ta3 import orderflow as O
    idx = pd.date_range("2026-01-05 09:30", periods=78 * 2, freq="5min")
    rng = np.random.default_rng(0); c = 100 + np.cumsum(rng.normal(0, 0.05, len(idx)))
    b = pd.DataFrame(dict(open=c, high=c + 0.05, low=c - 0.05, close=c, volume=rng.integers(100, 1000, len(idx))), index=idx)
    vw = O.session_vwap(b); assert (vw["upper_1.0"] >= vw.vwap).all()
    vp = O.volume_profile(b); assert vp["val"] <= vp["poc"] <= vp["vah"]
    t = pd.DataFrame(dict(price=[10.00, 10.01, 10.01, 10.00, 10.02], size=[5, 3, 4, 2, 6]),
                     index=pd.date_range("2026-01-05 09:30", periods=5, freq="s"))
    s = O.classify_ticks(t); assert list(s) == [1, 1, 1, -1, 1]
    bd = O.bar_delta(t, "1min"); assert bd.delta.iloc[0] == 5 + 3 + 4 - 2 + 6


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f(); print("ok ", name)
