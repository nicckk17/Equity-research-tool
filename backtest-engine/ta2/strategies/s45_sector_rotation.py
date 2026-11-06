"""S45 sector rotation. Cached bars only; python -m ta2 portfolio S45 [--config as_traded] [--window IS|OOS].
Use --self-test, or --config NAME --window IS --fees main --random-paths 5.
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass, asdict
from itertools import product
from pathlib import Path
import json
import time
import numpy as np
import pandas as pd

OUT = "S45"
SECTORS = ("XFN.TO", "XEG.TO", "XMA.TO", "XIT.TO", "XRE.TO", "XUT.TO")
WINDOWS = {"IS": ("2000-01-01", "2015-12-31"), "OOS": ("2016-01-01", "2024-10-31")}
COSTS = {"main": .0012, "low": .0005}

@dataclass(frozen=True)
class Spec:
    months: int = 6
    top: int = 3
    rebalance: str = "monthly"
    regime: bool = True
    @property
    def name(self):
        return f"rs{self.months}m_top{self.top}_{self.rebalance}_regime{int(self.regime)}"

def specs():
    return [Spec(*v) for v in product((3, 6, 12), (1, 2, 3), ("weekly", "monthly"), (False, True))]

NAMED = {"as taught (TSX adaptation)": Spec(6, 3, "weekly", True), "as traded": Spec()}

def clean(df):
    if df.empty:
        return pd.DataFrame(columns=["open", "close", "adj_close"], index=pd.DatetimeIndex([], name="date"))
    d = df.copy()
    d.index = pd.DatetimeIndex(pd.to_datetime(d.index)).tz_localize(None)
    d = d.sort_index().loc[:"2024-10-31"]
    if not d.index.is_unique:
        raise ValueError("Duplicate dates")
    x = d[["open", "close", "adj_close"]].to_numpy(float)
    return d.loc[np.isfinite(x).all(axis=1) & (x > 0).all(axis=1)]

class Panel:
    def __init__(self, data, benchmark):
        self.benchmark = clean(benchmark)
        self.cal = self.benchmark.index
        if len(self.cal) < 2:
            raise ValueError("XIU requires at least two valid bars")
        data = {s: clean(d) for s, d in sorted(data.items())}
        self.empty = [s for s, d in data.items() if d.empty]
        self.data = {s: d for s, d in data.items() if not d.empty}
        self.symbols = list(self.data)
        self.close = pd.DataFrame({s: d.adj_close.reindex(self.cal) for s, d in self.data.items()}, index=self.cal)
        self.opens = pd.DataFrame({s: (d.open*d.adj_close/d.close).reindex(self.cal) for s, d in self.data.items()}, index=self.cal)
        self.marks = self.close.ffill()
        self.cache = {}

    def schedule(self, spec):
        if spec.name in self.cache:
            return self.cache[spec.name]
        # RS = sector total return / index total return over exact calendar months.
        # As-of past endpoint only; no backfill and no pre-inception eligibility.
        past = self.cal.searchsorted(self.cal - pd.DateOffset(months=spec.months), side="right") - 1
        history = np.full(self.close.shape, np.nan)
        bh = np.full(len(self.cal), np.nan)
        good = past >= 0
        history[good] = self.marks.to_numpy()[past[good]]
        bm = self.benchmark.adj_close
        bh[good] = bm.to_numpy()[past[good]]
        score = (self.close / history).div(bm / bh, axis=0) - 1
        market = bm > bm.rolling(200, min_periods=200).mean()
        period = self.cal.to_period("W-FRI" if spec.rebalance == "weekly" else "M")
        result = {}
        for i in range(len(self.cal)-1):
            if period[i] == period[i+1]:
                continue
            signal, execution = self.cal[i:i+2]
            row = score.iloc[i].dropna().sort_values(ascending=False, kind="stable")
            pool = list(row.index) if not spec.regime or market.iloc[i] else []
            chosen = pool[:spec.top]
            result[execution] = (signal, chosen, pool)
        self.cache[spec.name] = result
        return result

def simulate(panel, spec, start, end, cost=.0012, seed=None):
    """Equal-weight targets at next open; missing exits wait for an actual bar.

    Random paths sample the same number of names from the same history-eligible sector universe.
    Full cash if no leaders. Long-only, fractional shares, no leverage.
    """
    cal = panel.cal[(panel.cal >= pd.Timestamp(start)) & (panel.cal <= pd.Timestamp(end))]
    if len(cal) < 2:
        raise ValueError("Insufficient benchmark window")
    schedule = panel.schedule(spec)
    symbols = panel.symbols
    op = panel.opens.loc[cal].to_numpy(float)
    cl = panel.close.loc[cal].to_numpy(float)
    mark = panel.marks.loc[cal].to_numpy(float)
    lookup = {s: i for i, s in enumerate(symbols)}
    shares = np.zeros(len(symbols)); cash = 1.; values = []; orders = []; fills = []
    pending = set(); rng = np.random.default_rng(seed)
    gaps = dict(held_missing_marks=0, deferred_exit_days=0, skipped_entries=0)
    desired = set()
    for i, date in enumerate(cal):
        available = np.isfinite(op[i])
        gaps["held_missing_marks"] += int(((shares > 0) & ~np.isfinite(cl[i])).sum())

        def fill(j, delta, reason):
            nonlocal cash
            px = op[i, j]; amount = abs(delta) * px
            opened = delta > 0 and shares[j] <= 1e-12
            closed = delta < 0 and shares[j] + delta <= 1e-12
            cash -= delta * px + cost * amount
            shares[j] += delta
            fills.append(dict(date=date, symbol=symbols[j], side="buy" if delta > 0 else "sell",
                              units=abs(delta), adjusted_price=px, notional=amount,
                              fee=cost * amount, reason=reason,
                              opened_position=opened, closed_position=closed))

        if date in schedule:
            signal, chosen, pool = schedule[date]
            if seed is not None:
                chosen = sorted(rng.choice(pool, size=len(chosen), replace=False).tolist())
            desired = {lookup[s] for s in chosen}
            pending = {j for j in range(len(symbols)) if shares[j] > 0 and j not in desired}
            orders.append(dict(date=date, signal_date=signal, selected=";".join(chosen),
                               eligible=len(pool), target_count=len(chosen)))
        for j in sorted(pending.copy()):
            if available[j]:
                fill(j, -shares[j], "rank_or_trend_exit"); pending.remove(j)
            else:
                gaps["deferred_exit_days"] += 1
        if date in schedule and i < len(cal) - 1:
            opening = np.where(available, op[i], mark[i])
            equity = cash + np.nansum(shares * opening)
            target = equity / len(desired) if desired else 0.
            # Sell excess before funding buys. Frozen holdings consume cash.
            for j in sorted(desired):
                if available[j] and shares[j] * op[i, j] > target:
                    fill(j, target / op[i, j] - shares[j], "rebalance")
            needs = {j: max(0., target - shares[j] * op[i, j]) for j in sorted(desired) if available[j]}
            total = sum(needs.values()) * (1 + cost)
            scale = min(1., max(0., cash) / total) if total else 0.
            for j, amount in needs.items():
                if amount > 1e-12 and scale > 0:
                    fill(j, amount * scale / op[i, j], "rebalance")
            gaps["skipped_entries"] += sum(not available[j] and shares[j] == 0 for j in desired)
        if cash < -1e-9 or (shares < -1e-9).any():
            raise AssertionError("Cash-only constraint violated")
        # Terminal equity stays marked at last known prices; no invented exit.
        values.append(cash + np.nansum(shares * mark[i]))
    return (pd.Series(values, index=cal, name="equity"),
            pd.DataFrame(fills, columns=["date", "symbol", "side", "units", "adjusted_price", "notional", "fee", "reason",
                                         "opened_position", "closed_position"]),
            pd.DataFrame(orders), {**gaps, "unresolved_exits": len(pending),
                                   "open_positions": int((shares > 0).sum())})


def metrics(curve):
    x = np.r_[1., curve.to_numpy()]
    years = (curve.index[-1] - curve.index[0]).days / 365.25
    return dict(end_value=float(x[-1]), cagr=float(x[-1] ** (1 / years) - 1),
                max_dd=float((x / np.maximum.accumulate(x) - 1).min()))


def run(panel, spec, window, fees, output, random_paths, seed_start=1000):
    output.mkdir(parents=True, exist_ok=True)
    start, end = WINDOWS[window]
    cost = COSTS[fees]
    curve, fills, orders, gaps = simulate(panel, spec, start, end, cost)
    tag = f"{spec.name}_{window}_{fees}_seed{seed_start}"
    curve.to_csv(output / f"{tag}_curve.csv")
    fills.to_csv(output / f"{tag}_fills.csv", index=False)
    orders.to_csv(output / f"{tag}_orders.csv", index=False)
    b = panel.benchmark.loc[curve.index]
    bh = b.adj_close / (b.open.iloc[0]*b.adj_close.iloc[0]/b.close.iloc[0]) / (1+cost)
    bh.to_csv(output / f"{tag}_XIU.csv")
    paths = []
    for seed in range(seed_start, seed_start+random_paths):
        rc, rf, _, rg = simulate(panel, spec, start, end, cost, seed)
        paths.append(dict(seed=seed, entries=int(rf.opened_position.sum()), **metrics(rc), **rg))
    pd.DataFrame(paths).to_csv(output / f"{tag}_random.csv", index=False)
    ends = [r["end_value"] for r in paths]
    sm = metrics(curve)
    summary = dict(config=spec.name, window=window, fees=fees,
                   entries=int(fills.opened_position.sum()), exits=int(fills.closed_position.sum()),
                   buys=int((fills.side == "buy").sum()), sells=int((fills.side == "sell").sum()),
                   **sm, **gaps, xiu_cagr=metrics(bh)["cagr"], xiu_max_dd=metrics(bh)["max_dd"],
                   random_end_mean=float(np.mean(ends)), random_end_p05=float(np.quantile(ends,.05)),
                   random_end_p95=float(np.quantile(ends,.95)),
                   descriptive_tail_fraction=(1+sum(e >= sm["end_value"] for e in ends))/(1+len(ends)))
    pd.DataFrame([summary]).to_csv(output / f"{tag}_summary.csv", index=False)
    manifest = dict(spec=asdict(spec), named={n:s.name for n,s in NAMED.items()},
                    requested_universe=SECTORS, empty_symbols_skipped=panel.empty,
                    coverage={s:dict(first=str(d.index[0].date()), last=str(d.index[-1].date()), bars=len(d)) for s,d in panel.data.items()},
                    benchmark_first=str(panel.cal[0].date()), window=WINDOWS[window], fees_per_side=cost,
                    random_paths=random_paths, seed_start=seed_start,
                    warnings=["Fixed current ETF universe; inception histories differ; no pre-inception backfill.",
                              "Tail fraction is descriptive; no multiple-testing correction.",
                              "RRG improving preference omitted: undefined in registry; pure RS adaptation.",
                              "Terminal holdings marked, not forcibly liquidated; cash earns zero."])
    (output / f"{tag}_manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print(json.dumps(summary), flush=True)


def synthetic():
    idx = pd.bdate_range("1998-01-01", "2024-10-31")
    t = np.arange(len(idx))
    def frame(j):
        c = 100*np.exp(.00015*t + .13*np.sin(t/(65+11*j)+j))
        return pd.DataFrame(dict(open=c*.999, close=c, adj_close=c), index=idx)
    return {s:frame(j+1) for j,s in enumerate(SECTORS)}, frame(0)


def self_test():
    data,bm = synthetic()
    p=Panel(data,bm); sp=Spec()
    assert len(specs()) == len({s.name for s in specs()}) == 36
    assert all(s in specs() for s in NAMED.values())
    for spec in NAMED.values():
        schedule=p.schedule(spec)
        for n in (330,811,1400):
            cut=bm.index[n-1]
            pp=Panel({s:d.loc[:cut] for s,d in data.items()},bm.loc[:cut])
            assert pp.schedule(spec)=={d:v for d,v in schedule.items() if d<=cut}
        a,f,o,g=simulate(p,spec,"2000-01-01","2024-10-31",cost=0)
        assert len(f)>100 and (o.date>o.signal_date).all()
    a,f,o,g=simulate(p,sp,"2000-01-01","2024-10-31",cost=0)
    scaled=Panel({s:d*7 for s,d in data.items()},bm*3)
    np.testing.assert_allclose(a,simulate(scaled,sp,"2000-01-01","2024-10-31",cost=0)[0])
    cut=pd.Timestamp("2005-06-15")
    changed={s:d.copy() for s,d in data.items()}
    for d in changed.values():
        d.loc[d.index>cut]*=.5
    b,bf,bo,_=simulate(Panel(changed,bm),sp,"2000-01-01","2024-10-31",cost=0)
    np.testing.assert_allclose(a.loc[:cut],b.loc[:cut])
    pd.testing.assert_frame_equal(f[f.date<=cut],bf[bf.date<=cut])
    pd.testing.assert_frame_equal(o[o.date<=cut],bo[bo.date<=cut])
    r1=simulate(p,sp,"2000-01-01","2002-12-31",seed=7)[0]
    np.testing.assert_array_equal(r1,simulate(p,sp,"2000-01-01","2002-12-31",seed=7)[0])
    # Exact fee algebra, deferred exit and no phantom fills.
    flat=bm.copy(); flat.loc[:,:]=100.
    fp=Panel({"A":flat},flat)
    d0,d1,d2=bm.index[300:303]
    fp.cache[sp.name]={d0:(bm.index[299],["A"],["A"]),d1:(d0,[],[])}
    fc,ff,_,_=simulate(fp,sp,str(d0),str(bm.index[310]),cost=.01)
    np.testing.assert_allclose(fc.iloc[0],1/1.01)
    np.testing.assert_allclose(fc.iloc[1:],.99/1.01)
    fp.opens.loc[d1,"A"]=np.nan; fp.close.loc[d1,"A"]=np.nan
    fc,ff,_,gg=simulate(fp,sp,str(d0),str(bm.index[310]),cost=.01)
    assert ff.iloc[-1].date==d2 and gg["deferred_exit_days"]==1
    np.testing.assert_allclose(fc.iloc[1],1/1.01)
    late=dict(data); late[SECTORS[0]]=data[SECTORS[0]].loc["2010-01-01":]
    late["EMPTY"]=pd.DataFrame()
    lp=Panel(late,bm)
    assert lp.empty==["EMPTY"]
    assert all(SECTORS[0] not in pool for d,(_,_,pool) in lp.schedule(sp).items() if d < pd.Timestamp("2010-07-01"))
    # All-empty sectors must remain cash without failing.
    ep=Panel({"EMPTY":pd.DataFrame()},bm)
    np.testing.assert_allclose(simulate(ep,sp,"2000-01-01","2001-12-31")[0],1.)
    print("PASS: 36 unique specs, named trade counts, prefix/future invariance, scale symmetry, seeded random, fees, gaps, late/empty histories")


def main():
    timer=time.perf_counter()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test",action="store_true")
    parser.add_argument("--synthetic",action="store_true")
    parser.add_argument("--list-configs",action="store_true")
    parser.add_argument("--config",default="as_traded")
    parser.add_argument("--window",choices=WINDOWS,default="IS")
    parser.add_argument("--fees",choices=COSTS,default="main")
    parser.add_argument("--random-paths",type=int,default=5)
    parser.add_argument("--seed-start",type=int,default=1000)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    if args.self_test:
        self_test()
    elif args.list_configs:
        print("as_taught, as_traded\n"+"\n".join(s.name for s in specs()))
    else:
        if not 1<=args.random_paths<=20:
            parser.error("Use 1..20 random paths per slice; vary --seed-start for additional paths")
        choices={s.name:s for s in specs()}
        choices.update(as_taught=list(NAMED.values())[0],as_traded=Spec())
        if args.config not in choices:
            parser.error("Unknown config; use --list-configs")
        missing=[]
        if args.synthetic:
            data,bm=synthetic()
        else:
            from ..data import load
            def cached(s):
                try:
                    return load(s)  # Never request holdout.
                except (FileNotFoundError,pd.errors.EmptyDataError):
                    missing.append(s)
                    return pd.DataFrame()
            data={s:cached(s) for s in SECTORS}
            bm=cached("XIU.TO")
        output=args.output or Path(__file__).resolve().parents[2]/"results"/"ta2"/OUT
        run(Panel(data,bm),choices[args.config],args.window,args.fees,output,args.random_paths,args.seed_start)
        print("Missing files:",missing)
    print(f"Elapsed: {time.perf_counter()-timer:.3f} s",flush=True)

if __name__=="__main__":
    main()

TIER = "protection"
EVIDENCE = ("As traded: TSX IS 5.3%/-39% vs XIU 5.2%/-52%; OOS 9.4%/-16% vs 10.8%/-35%; beats random sector picks by ~3%/yr. US version: random sectors do as well (the protection is the regime filter). Same money as the index, less than half the crash.")
