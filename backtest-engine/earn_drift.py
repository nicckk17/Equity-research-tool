"""Post-earnings drift event study (Claude, 2026-11-05). Run from tsx-ta with PYTHONPATH=.
Reaction = close(E+1)/close(E-1)-1 (2 days, covers before-open AND after-close reports).
Drift = return from close(E+1) to close(E+1+h), signed in the reaction's direction, minus the index over the same days."""
import numpy as np, pandas as pd
from ta2 import data as D
import ta3.config as C3
syms = [s for s in C3.UNIVERSES["TSX"]["symbols"] if not s.startswith("^")]
idx = None
for cand in ["XIU.TO", "^GSPTSE"]:
    try:
        idx = D.load(cand, "TSX").close; break
    except Exception:
        pass
H = [1, 2, 3, 5, 10, 20, 40, 60]
rows = []
for s in syms:
    try:
        df = D.load(s, "TSX"); ed = D.earnings(s, "TSX")
    except Exception:
        continue
    c = df.close.astype(float); n = len(c)
    ic = idx.reindex(c.index).ffill() if idx is not None else None
    tr = pd.concat([df.high - df.low, (df.high - c.shift()).abs(), (df.low - c.shift()).abs()], axis=1).max(axis=1)
    atrp = (tr.rolling(20).mean() / c).to_numpy()
    for d in pd.to_datetime(ed):
        E = c.index.searchsorted(d)
        if E < 21 or E + 1 + max(H) >= n:
            continue
        r_day = c.iloc[E] / c.iloc[E - 1] - 1
        r2 = c.iloc[E + 1] / c.iloc[E - 1] - 1
        if r2 == 0 or not np.isfinite(r2):
            continue
        sgn = np.sign(r2); row = dict(sym=s, date=c.index[E], year=c.index[E].year, react=r2, react_day=r_day,
                                     react_atr=abs(r2) / atrp[E - 1] if atrp[E - 1] > 0 else np.nan, dirn="up" if sgn > 0 else "down")
        for h in H:
            f = c.iloc[E + 1 + h] / c.iloc[E + 1] - 1
            fi = (ic.iloc[E + 1 + h] / ic.iloc[E + 1] - 1) if ic is not None else 0.0
            row[f"d{h}"] = sgn * f * 100; row[f"x{h}"] = sgn * (f - fi) * 100
        rows.append(row)
R = pd.DataFrame(rows)
R["size"] = pd.qcut(R.react_atr, 3, labels=["small", "medium", "big"])
R["period"] = np.where(R.year <= 2015, "2002-15", "2016-24")
def tab(g):
    out = {}
    for h in H:
        out[f"{h}d"] = f"{g[f'x{h}'].mean():+.2f}% ({(g[f'x{h}'] > 0).mean() * 100:.0f}%)"
    out["n"] = len(g); return pd.Series(out)
pd.set_option("display.width", 250)
print("index used:", "yes" if idx is not None else "NO (raw returns)")
print("events:", len(R), "symbols:", R.sym.nunique(), R.date.min().date(), "->", R.date.max().date())
print("\nAvg continuation in the earnings direction, index-adjusted (hit rate), held from close of E+1:")
print("ALL"); print(tab(R).to_frame().T.to_string())
for col in ["dirn", "size", "period"]:
    print(f"\nby {col}"); print(R.groupby(col, observed=True).apply(tab).to_string())
print("\nbig moves by direction"); print(R[R["size"] == "big"].groupby("dirn").apply(tab).to_string())
print("\nbig moves by direction & period"); print(R[R["size"] == "big"].groupby(["dirn", "period"]).apply(tab).to_string())
# t-stats for big moves
from scipy import stats
for dname in ["up", "down"]:
    g = R[(R["size"] == "big") & (R.dirn == dname)]
    print(dname, "big t-stat:", {h: round(stats.ttest_1samp(g[f"x{h}"], 0).statistic, 2) for h in H})
R.to_csv("results/ta3/earn_drift_events.csv", index=False)
