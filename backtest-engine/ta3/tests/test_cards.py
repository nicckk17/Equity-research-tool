"""Read-only smoke/causality checks. Claude runs this; no strategy installation needed.

python -B test_cards.py --root ".../AI Equity research/tsx-ta"
Optional: --exhaustive checks every planned config for price-prefix invariance.
No sweeps/results/ledger are written, no downloads and no synthetic trade fallback.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
MODULES = ("bb200", "erg_s53", "erg_s55", "hi52", "athd", "dens", "earn")

def load_module(name):
    spec = importlib.util.spec_from_file_location("cards_" + name, HERE / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=HERE.parents[1] / "tsx-ta")
    parser.add_argument("--exhaustive", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(args.root.resolve()))
    import numpy as np
    import pandas as pd
    from ta2 import data as D
    from ta2.indicators import context
    from ta3 import sweep as W
    from ta3.knobs import defaults, plan
    from ta3.research import validate

    mods = {name: load_module(name) for name in MODULES}
    earn = mods["earn"]

    def read_bars(sym, universe="TSX", tf="D", holdout=False):
        assert tf == "D" and not holdout
        # Avoid S.load/D.load: their path helpers call mkdir inside the source tree.
        store = args.root / "data" / "store" / universe / "D" / (sym + ".parquet")
        if store.exists():
            df = pd.read_parquet(store)
            return df[df.index < pd.Timestamp(W.C.HOLDOUT[0])]
        path = D.C.DATA / D.C.UNIVERSES[universe]["dir"] / "bars" / (sym + ".csv")
        return D.clean(pd.read_csv(path)).set_index("date")

    def dates(sym):
        path = D.C.DATA / D.C.UNIVERSES["TSX"]["dir"] / "earnings" / (sym + ".csv")
        if not path.exists() or not path.stat().st_size:
            raise AssertionError(f"Missing real earnings file: {path}")
        return pd.to_datetime(pd.read_csv(path)["date"]).dropna().drop_duplicates().sort_values()

    class Cards(unittest.TestCase):
        def test_cards_and_plans(self):
            cards = {p.stem: validate(json.loads(p.read_text(encoding="utf-8"))) for p in HERE.glob("*.json")}
            self.assertEqual(set(cards), {"BB200", "ERG", "HI52", "ATHD", "DENS", "EARN"})
            for card in cards.values():
                self.assertEqual(card["status"], "approved")
            total = 0
            for name, mod in mods.items():
                configs = plan(mod.KNOBS)
                self.assertTrue(configs, name)
                self.assertTrue(any("baseline" in tags for _, tags in configs))
                self.assertTrue(set(mod.SIGNAL_KNOBS) <= set(mod.KNOBS))
                total += len(configs)
                print(f"{name}: {len(configs)} planned configurations", flush=True)
            self.assertLessEqual(total, 1500, f"Combined plan is {total}")

        def test_baselines(self):
            for name, mod in mods.items():
                for sym in ("RY.TO", "SU.TO"):
                    with self.subTest(module=name, symbol=sym):
                        with patch.object(W, "strategy", return_value=mod), patch.object(W.S, "load", side_effect=read_bars):
                            prep = W.Prep(mod.KEY, universe="TSX", tf="D", only=[sym])
                        self.assertEqual(len(prep.items), 1, f"No usable daily history: {sym}")
                        if name == "earn":
                            it = prep.items[0]
                            it["ctx"] = earn.attach_earnings(it["df"], it["ctx"], dates(sym))
                        trades = W.run_config(prep, defaults(mod.KNOBS), seed=7)
                        self.assertGreaterEqual(len(trades), 1, "No real-data baseline trade")
                        for col in ("R", "rn", "entry", "exit_px"):
                            self.assertTrue(np.isfinite(trades[col]).all(), col)
                        self.assertTrue(trades.R.gt(0).all())
                        print(f"{name} {sym}: {len(trades)} baseline trades", flush=True)

        def test_no_future_price_dependency(self):
            for sym in ("RY.TO", "SU.TO"):
                df = read_bars(sym)
                self.assertGreater(len(df), 600)
                full_ctx = context(df)
                event_dates = dates(sym)
                for name, mod in mods.items():
                    configs = plan(mod.KNOBS, parts=("oat",) if not args.exhaustive else ("oat", "pairs", "grid"))
                    for cfg, _ in configs:
                        ctx = earn.attach_earnings(df, full_ctx, event_dates) if name == "earn" else full_ctx
                        raw = mod.raw_signals(df, ctx, cfg)
                        sg = mod.signals(raw, cfg)
                        full_lines = mod.lines(df, ctx, cfg)
                        # Include actual signal boundaries, including scheduled E-1 with E deleted.
                        cuts = {len(df) // 2, len(df) * 3 // 4, len(df) - 2}
                        ts = sg.t.to_numpy(int)
                        if len(ts):
                            cuts.update(int(t) for t in (ts[0], ts[len(ts)//2], ts[-1]))
                        for t in sorted(cuts):
                            prefix = df.iloc[:t + 1]
                            short_ctx = context(prefix)
                            if name == "earn":
                                short_ctx = earn.attach_earnings(prefix, short_ctx, event_dates, calendar=df.index)
                            pr = mod.raw_signals(prefix, short_ctx, cfg)
                            ps = mod.signals(pr, cfg)
                            with self.subTest(module=name, symbol=sym, cfg=cfg, t=t):
                                pd.testing.assert_frame_equal(raw[raw.t <= t].reset_index(drop=True), pr.reset_index(drop=True))
                                pd.testing.assert_frame_equal(sg[sg.t <= t].reset_index(drop=True), ps.reset_index(drop=True))
                                for key, values in mod.lines(prefix, short_ctx, cfg).items():
                                    np.testing.assert_allclose(full_lines[key][:t + 1], values, equal_nan=True)

        def test_earn_unsupported_stop_is_explicit(self):
            with self.assertRaises(NotImplementedError):
                earn.exit_recipe({**defaults(earn.KNOBS), "stop": "none"})
            df = read_bars("RY.TO")
            with self.assertRaises(ValueError):
                earn.raw_signals(df, context(df), defaults(earn.KNOBS))

        def test_erg_default_base_and_lag(self):
            for name in ("erg_s53", "erg_s55"):
                mod = mods[name]
                df = read_bars("RY.TO")
                ctx = context(df)
                k = defaults(mod.KNOBS)
                raw = mod.raw_signals(df, ctx, k)
                b = mod._base()
                original = mod.BASE.signals(mod.BASE.raw_signals(df, ctx, b), b)
                pd.testing.assert_frame_equal(raw[original.columns], original)
                c = df.close.astype(float)
                den = c.diff().abs().rolling(k["er_len"]).sum()
                er = ((c - c.shift(k["er_len"])).abs() / den.where(den > 0)).mask(den.eq(0), 0)
                np.testing.assert_allclose(raw.er_prev, er.shift().iloc[raw.t].to_numpy(), equal_nan=True)

    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Cards))
    return 0 if result.wasSuccessful() else 1

if __name__ == "__main__":
    raise SystemExit(main())
