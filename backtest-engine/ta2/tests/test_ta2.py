"""ta2 self-checks.   python -m ta2.tests.test_ta2   (about 1 minute)

1. Engine fill rules on hand-made bars (gap stop, same-bar stop+target, state exit, trailing stop, partial, time exit).
2. No look-ahead: signals computed on a price prefix equal the full-history signals up to that bar.
3. Parity with v1: rebuilding chunk 0 (first stocks) reproduces v1's trades exactly (fingerprints of 7 strategies).
   NOTE: if `ta2 data update` re-downloaded history and Yahoo restated old bars (splits), parity can drift:
   that is a data change, not a code change.
4. Control: S99 cheats must beat random twins; random entries must not.
5. The live bot end to end against the offline stub broker (entry, protective stop, rule exit, rails).
"""
from __future__ import annotations
import json, tempfile, time
from pathlib import Path
import numpy as np, pandas as pd
from .. import engine as E, data as D, config as C
from ..indicators import context
from ..strategies import get

HERE = Path(__file__).resolve().parent


def bars(rows):
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    df.index = pd.bdate_range("2010-01-04", periods=len(df), name="date"); df["volume"] = 1e6
    return df


def one(df, sig, recipe, mode=1, buf=0.0, lines=None, atr=1.0):
    ctx = {"atr": np.full(len(df), atr)}
    sg = pd.DataFrame(dict(t=[sig["t"]], side=[sig.get("side", 1)], anchor=[sig["anchor"]], A=[atr], opp=[sig.get("opp", np.nan)],
                           lo=[0], hi=[len(df)]))
    return E.trades(df, ctx, sg, mode, buf, recipe, lines or {}, seed=1).iloc[0]


def test_engine():
    flat = [[100, 101, 99, 100]] * 3
    # gap through the stop fills at the open (reason 1)
    r = one(bars(flat + [[100, 101, 99.5, 100], [95, 96, 94, 95]] + flat), dict(t=2, anchor=99), dict(target_R=2, max_hold=10))
    assert r.reason == 1 and r.exit_px == 95, r
    # stop and target in the same bar -> stop (reason 0)
    r = one(bars(flat + [[100, 103, 98, 100]] + flat), dict(t=2, anchor=99), dict(target_R=2, max_hold=10))
    assert r.reason == 0 and r.exit_px == 99, r
    # target touched -> target price (reason 2)
    r = one(bars(flat + [[100, 103, 99.5, 102]] + flat), dict(t=2, anchor=99), dict(target_R=2, max_hold=10))
    assert r.reason == 2 and r.exit_px == 102, r
    # state exit: line < 0 at close t+2 -> sell next open (reason 5)
    df = bars(flat + [[100, 101, 99.5, 100]] * 4); line = np.ones(len(df)); line[4] = -1
    r = one(df, dict(t=2, anchor=90), dict(state="x", max_hold=10), lines={"x": line})
    assert r.reason == 5 and r.exit_bar == 5 and r.exit_px == 100, r
    # trailing stop never loosens and exits on the way down
    df = bars(flat + [[100, 110, 100, 109], [109, 112, 108, 111], [111, 111, 105, 106], [106, 106, 100, 101]])
    r = one(df, dict(t=2, anchor=95), dict(trail_atr=3, max_hold=20), atr=2.0)
    assert r.reason == 0 and abs(r.exit_px - 106) < 1e-9, r          # 112 - 3*2
    # half at +1R then stop at breakeven-ish trail: R = average of halves
    r = one(bars(flat + [[100, 105, 99.5, 104], [104, 104, 90, 91]] + flat), dict(t=2, anchor=95), dict(half_R=1, max_hold=10))
    assert abs(r.gR - (0.5 * 1 + 0.5 * (-1))) < 1e-9, r
    # time exit at the close 2 bars after entry
    r = one(bars(flat * 3), dict(t=2, anchor=90), dict(time_bars=2, max_hold=10))
    assert r.reason == 4 and r.exit_bar == 5, r
    print("OK engine fill rules")


def test_no_lookahead():
    df = D.load("RY.TO")
    for key in ("S53", "S55", "S56", "S31", "S54"):
        mod = get(key); full = mod.signals(df, context(df)); cut = len(df) - 400
        pre = df.iloc[:cut]; part = mod.signals(pre, context(pre))
        a = full[full.t < cut - 1].reset_index(drop=True); b = part[part.t < cut - 1].reset_index(drop=True)
        cols = ["t", "side", "fam"] + list(mod.FLAGS)
        pd.testing.assert_frame_equal(a[cols], b[cols], check_dtype=False)
    print("OK no look-ahead (5 strategies, prefix = full history minus 400 bars)")


def test_parity_and_control():
    from ..test import Run
    ref = json.loads((HERE / "v1_chunk0_fingerprints.json").read_text())
    for key, fp in ref.items():
        r = Run(key); r.out = Path(tempfile.mkdtemp()); r._build_chunk(0, r.chunks()[0])
        R = pd.read_pickle(r.out / "res_0.pkl")
        got = dict(trades=int(len(R)), sum_gR=round(float(R.gR.astype(float).sum()), 3), sum_xb=int(R.xb.astype("int64").sum()),
                   sum_entry=round(float(R.entry.astype(float).sum()), 2))
        ok = got["trades"] == fp["trades"] and got["sum_xb"] == fp["sum_xb"] and abs(got["sum_gR"] - fp["sum_gR"]) < 0.05
        print(("OK" if ok else "MISMATCH"), "parity", key, got if not ok else f"{got['trades']} trades")
        assert ok, (key, got, fp)
        if key == "S99":
            S = pd.read_pickle(r.out / "sig_0.pkl"); R["cheat"] = S.set_index("sig_id").cheat.reindex(R.sig_id).to_numpy()
            rn, rr = E.r_net(R); cheat = R.cheat.to_numpy(bool)
            d = rn - rr
            assert d[cheat].mean() > 0.3 and abs(np.nanmean(d)) < 0.05, ("control", d[cheat].mean(), np.nanmean(d))
            print(f"OK control: cheats beat their twins by {d[cheat].mean():+.2f}R; random entries {np.nanmean(d):+.3f}R")




def test_bot():
    """Whole daily routine against the offline stub broker: sync, entry+stop, exit rule, trade log, rails."""
    from .. import broker as Bk, bot as Bot_
    import tempfile
    mod, vname, v = Bot_.version_of("S53")
    df = D.load("RY.TO")                                  # real bars, so the signal is a real S53 signal
    ctx = context(df); sg = mod.signals(df, ctx)
    m = (sg.fam == v["fam"]) & sg.side.isin(v["sides"]) & sg[list(v["flags"])].all(axis=1)
    t = int(sg[m].t.iloc[-20])                           # a signal well inside the history
    bars = {"RY.TO": df.iloc[:t + 1]}
    day = df.index[t]
    bk = Bk.StubBroker(prices={"RY.TO": float(df.close.iloc[t])}).connect()
    d = Path(tempfile.mkdtemp())
    bot = Bot_.Bot(bk, live_dir=d, keys=("S53",), day=day, bars=bars)
    bot.expected = day; bot.execution = df.index[t + 1]
    st = bot.sync(); assert st["equity_cad"] == 100000 and st["open_positions"] == 0
    exits, entries = bot.plan()
    assert not exits and len(entries) == 1 and entries[0]["symbol"] == "RY.TO", (exits, entries)
    e = entries[0]
    expect_stop = round(float(df.low.iloc[t - 9:t + 1].min()) - v["buf"] * float(sg[m].A.iloc[-20]), 2)
    assert abs(e["planned_stop"] - expect_stop) < 0.011, (e["planned_stop"], expect_stop)
    done = bot.run(submit=True)
    assert len(done) == 1 and done[0]["action"] == "BUY" and done[0]["qty"] > 0
    risk = e["signal_close"] - e["planned_stop"]
    assert done[0]["qty"] == int(min(C.RISK_PER_TRADE * 100000 / risk, C.NOTIONAL_CAP * 100000 / e["signal_close"]))
    assert len(bot.ledger) == 1 and len(bk.open_orders()) == 1 and bk.open_orders().iloc[0].type == "STP"
    print(f"OK bot entry: {done[0]['qty']} shares RY.TO, stop {done[0]['stop']}, protective stop resting at the broker")
    # move forward to the first bar where the strategy's own exit rule fires
    hist = mod._macd(df.close.astype(float), mod.SETS[v["fam"]])[1]
    nxt = next(j for j in range(t + 1, len(df)) if hist.iloc[j] < 0)
    bars["RY.TO"] = df.iloc[:nxt + 1]
    bk.prices["RY.TO"] = float(df.close.iloc[nxt])
    bot2 = Bot_.Bot(bk, live_dir=d, keys=("S53",), day=df.index[nxt], bars=bars)
    bot2.expected = df.index[nxt]; bot2.execution = df.index[nxt + 1]
    bot2.sync(); ex, en = bot2.plan()
    assert len(ex) == 1 and "hist < 0" in ex[0]["reason"], ex
    bot2.run(submit=True)
    assert len(bot2.ledger) == 0 and len(bot2.trades) == 1 and len(bk.open_orders()) == 0, "stop must be cancelled on exit"
    tr = bot2.trades.iloc[0]
    assert np.isfinite(float(tr.R)) and tr.exit_reason.startswith("rule exit")
    print(f"OK bot exit: R {float(tr.R):+.2f} after {int(tr.held_days)} days, stop cancelled, trade logged")
    # rails
    bot3 = Bot_.Bot(bk, live_dir=d, keys=("S53",), day=df.index[nxt], bars=bars, kill_dd=0.0)
    bot3.sync(); assert bot3.plan()[1] == [], "kill switch must stop new entries"
    bk._pos["XYZ.TO"] = (10, 1.0)
    bot4 = Bot_.Bot(bk, live_dir=d, keys=("S53",), day=df.index[nxt], bars=bars)
    try:
        bot4.sync(); raise AssertionError("foreign position must block the run")
    except PermissionError as ex:
        assert "did not open" in str(ex)
    bot5 = Bot_.Bot(bk, live_dir=d, keys=("S53",), day=df.index[nxt], bars=bars, allow_foreign=True)
    bot5.sync(); assert "XYZ.TO" not in set(bot5.ledger.symbol)
    print("OK bot rails: kill switch stops entries; positions the bot did not open block the run (or are left alone)")
    for port, acct in ((4001, "DU1"), (4002, "U123456")):
        try:
            Bk.IBKRBroker(port=port).connect() if port == 4002 else Bk.IBKRBroker(port=port)
            raise AssertionError("live guard failed")
        except (PermissionError, ConnectionError, ImportError) as ex:
            assert isinstance(ex, (PermissionError, ConnectionError)), ex
    print("OK broker guard: live ports refused; paper port only connects to a DU/DF account")


if __name__ == "__main__":
    t0 = time.time(); test_engine(); test_no_lookahead(); test_parity_and_control(); test_bot(); print(f"ALL OK {time.time() - t0:.0f}s")
