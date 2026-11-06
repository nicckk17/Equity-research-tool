"""S64 'skip September' calendar rule (Canadian calendar claims, v1 S64_S68). TIER: WEAK.

Rule: hold the index ETF (XIU / SPY, dividends reinvested) every month except September. Sell at the first
open of September, buy back at the first open of October. Cash earns 0 (v1) unless --tbill.
Same kernel as v1 timing_kernel (fills at the dividend-adjusted open, cost per side).
  python -m ta2 portfolio S64 [--universe US] [--tbill] [--months 9]
"""
from __future__ import annotations
import argparse
import numpy as np, pandas as pd
from .. import config as C, data as D

TIER = "weak"
EVIDENCE = ("Skip September beat or tied buy-and-hold in all 4 windows: TSX IS 7.0% vs 5.2%, OOS 10.5% vs 10.8% (tie), "
            "US IS 5.1% vs 4.0%, OOS 15.8% vs 14.4%. Thin evidence: ~16 Septembers per window, no random control. "
            "Rejected siblings: sell in May (May-Oct), all S68 deposit-timing rules (= monthly SIP).")


def run(universe="TSX", months=(9,), cost=C.COST_MAIN, tbill=False):
    sym = C.UNIVERSES[universe]["bench"]; df = D.load(sym, universe)
    rows = []
    for w, (a, b) in {"IS": C.IS, "OOS": C.OOS}.items():
        f = df.loc[a:b]
        op = (f.open * f.adj_close / f.close).to_numpy(float); cl = f.adj_close.to_numpy(float)
        rate = (D.tbill(universe).reindex(f.index, method="ffill").fillna(0).to_numpy() / 100 / 252) if tbill else np.zeros(len(f))
        yrs = (f.index[-1] - f.index[0]).days / 365.25
        for name, hold in (("buy_hold", np.ones(len(f), bool)), ("skip " + ",".join(map(str, months)), ~np.isin(f.index.month, months))):
            cash, units, eq = 1.0, 0.0, np.empty(len(f))
            for i in range(len(f)):
                cash *= 1 + rate[i]
                if hold[i] and units == 0.0:
                    units = cash / (op[i] * (1 + cost)); cash = 0.0
                elif not hold[i] and units > 0.0:
                    cash = units * op[i] * (1 - cost); units = 0.0
                eq[i] = cash + units * cl[i]
            if units > 0:
                eq[-1] -= units * cl[-1] * cost
            a1 = np.r_[1.0, eq]
            rows.append(dict(universe=universe, window=w, strategy=name, cagr=round((eq[-1] ** (1 / yrs) - 1) * 100, 2),
                             max_dd=round(float(np.min(a1 / np.maximum.accumulate(a1) - 1)) * 100, 1)))
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--universe", default="TSX"); ap.add_argument("--tbill", action="store_true")
    ap.add_argument("--months", default="9")
    a = ap.parse_args()
    r = run(a.universe, tuple(int(m) for m in a.months.split(",")), tbill=a.tbill)
    out = C.RESULTS / "S64"; out.mkdir(parents=True, exist_ok=True); r.to_csv(out / f"skip_{a.universe}.csv", index=False)
    print(r.to_string(index=False))
