"""S43 standalone: python -m ta2 portfolio S43 [--grid] [--random-paths 100].

Cached data only; holdout never opened. --self-test uses synthetic numpy/pandas data.
See s43_rs_leaders_notes.md for the fixed, prespecified adaptations.
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass, asdict
from itertools import product
from pathlib import Path
import json
import numpy as np
import pandas as pd

OUT = "S43"
WINDOWS = {"IS": ("2000-01-01", "2015-12-31"),
           "OOS": ("2016-01-01", "2024-10-31")}
COSTS = {"main": .0012, "low": .0005}
# Fixed economic proxies, not inferred from subsequent stock performance.
SECTORS = {}
for _etf, _names in {
    "XFN.TO": "RY TD BNS BMO CM NA MFC SLF GWO POW IFC FFH BN BAM",
    "XEG.TO": "ENB TRP PPL SU CNQ CVE IMO TOU ARX",
    "XMA.TO": "CCO TECK-B FM NTR CCL-B",
    "XGD.TO": "ABX AEM WPM FNV K",
    "XIT.TO": "GIB-A OTEX SHOP CSU CLS",
    "XUT.TO": "FTS EMA H",
}.items():
    SECTORS.update({s + ".TO": _etf for s in _names.split()})


@dataclass(frozen=True)
class Spec:
    weeks: int = 26
    top: float = .20
    rebalance: str = "weekly"
    relative: str = "dual"

    @property
    def name(self):
        return f"rs{self.weeks}_top{self.top:.2f}_{self.rebalance}_{self.relative}"


def specs():
    return [Spec(*x) for x in product((13, 26, 52), (.10, .20, .30),
                                     ("weekly", "monthly"), ("index", "dual"))] + [Spec(26, .15)]


NAMED = {"as taught (85th percentile adaptation)": Spec(26, .15),
         "as traded": Spec()}


def clean(df):
    """No imputation of executable bars. Missing/invalid rows become gaps."""
    if df.empty:
        return pd.DataFrame(columns=["open", "close", "adj_close"],
                            index=pd.DatetimeIndex([], name="date"))
    d = df.copy()
    d.index = pd.DatetimeIndex(pd.to_datetime(d.index)).tz_localize(None)
    d = d.sort_index()
    if not d.index.is_unique:
        raise ValueError("Duplicate dates")
    d = d.loc[:"2024-10-31"]
    x = d[["open", "close", "adj_close"]].to_numpy(float)
    return d.loc[np.isfinite(x).all(axis=1) & (x > 0).all(axis=1)]


class Panel:
    """Reusable causal daily/weekly data; no backward fill, no ETF backfill."""
    def __init__(self, data, benchmark, sectors):
        self.benchmark = clean(benchmark)
        self.cal = self.benchmark.index
        if len(self.cal) < 2:
            raise ValueError("XIU requires at least two valid bars")
        self.data = {s: clean(d) for s, d in sorted(data.items())}
        self.empty = [s for s, d in self.data.items() if d.empty]
        self.data = {s: d for s, d in self.data.items() if not d.empty}
        self.symbols = list(self.data)
        if not self.symbols:
            raise ValueError("No nonempty stocks")
        self.close = pd.DataFrame({s: d.adj_close.reindex(self.cal) for s, d in self.data.items()})
        self.opens = pd.DataFrame({s: (d.open * d.adj_close / d.close).reindex(self.cal)
                                  for s, d in self.data.items()})
        self.marks = self.close.ffill()
        periods = self.cal.to_period("W-FRI")
        first = pd.Series(self.cal, index=periods).groupby(level=0).first()
        last = pd.Series(self.cal, index=periods).groupby(level=0).last()
        # A week is known complete only once a later week's session exists.
        self.dates = pd.DatetimeIndex(last.iloc[:-1].to_numpy())
        self.execution = dict(zip(self.dates, first.iloc[1:].to_numpy()))
        self.weekly = self.close.loc[self.dates]
        self.bw = self.benchmark.adj_close.reindex(self.dates)
        self.sw = {s: clean(d).adj_close.reindex(self.dates) for s, d in sectors.items()}
        self.cache = {}

    def features(self, spec):
        w = self.weekly
        stock_return = w / w.shift(spec.weeks) - 1
        index_return = self.bw / self.bw.shift(spec.weeks) - 1
        ix = (1 + stock_return).div(1 + index_return, axis=0) - 1
        score = ix.copy()
        sector_excess = pd.DataFrame(np.nan, index=w.index, columns=w.columns)
        sector_ok = pd.DataFrame(True, index=w.index, columns=w.columns)
        for s in w:
            etf = SECTORS.get(s)
            if etf is not None:
                sec = self.sw.get(etf, pd.Series(np.nan, index=w.index))
                sr = sec / sec.shift(spec.weeks) - 1
                sector_excess[s] = (1 + stock_return[s]) / (1 + sr) - 1
                # Murphy top-down: sector ratio rising over same horizon.
                if spec.relative == "dual":
                    score[s] = (ix[s] + sector_excess[s]) / 2
                    sector_ok[s] = (sr > index_return) & (stock_return[s] > sr)
        trend = w > w.rolling(10, min_periods=10).mean()
        market = self.bw > self.bw.rolling(40, min_periods=40).mean()
        return score, ix, sector_excess, sector_ok, trend, market

    def ranking_frame(self, spec):
        score, ix, sx, sector_ok, trend, market = self.features(spec)
        irank = ix.rank(axis=1, pct=True)
        srank = sx.rank(axis=1, pct=True)
        rank = score.rank(axis=1, ascending=False, method="first")
        frames = []
        for s in self.symbols:
            frames.append(pd.DataFrame(dict(signal_date=self.dates, symbol=s,
                execution_date=[self.execution[d] for d in self.dates], sector_etf=SECTORS.get(s, "XIU.TO proxy"),
                rs_index=ix[s].to_numpy(), rs_sector=sx[s].to_numpy(), score=score[s].to_numpy(),
                index_rank_pct=irank[s].to_numpy(),
                sector_rank_pct=srank[s].to_numpy(),
                score_rank=rank[s].to_numpy(),
                trend_ok=trend[s].to_numpy(), sector_ok=sector_ok[s].to_numpy(),
                market_ok=market.to_numpy())))
        return pd.concat(frames, ignore_index=True)

    def schedule(self, spec):
        if spec.name in self.cache:
            return self.cache[spec.name]
        score, ix, _, sector_ok, trend, market = self.features(spec)
        w = self.weekly
        result = {}
        for date in w.index:
            execution = pd.Timestamp(self.execution[date])
            if spec.rebalance == "monthly" and execution.month == date.month:
                continue
            row = score.loc[date].dropna().sort_values(ascending=False, kind="stable")
            n = max(1, int(np.ceil(spec.top * len(row)))) if len(row) else 0
            # Top cut is measured across history-eligible stocks BEFORE gates.
            gate = trend.loc[date] & sector_ok.loc[date] & (ix.loc[date] > 0) & bool(market.loc[date])
            chosen = [s for s in row.index[:n] if gate[s]]
            pool = [s for s in row.index if gate[s]]
            result[execution] = (date, chosen, pool)
        self.cache[spec.name] = result
        return result


def simulate(panel, spec, start, end, cost=.0012, seed=None):
    """Equal-weight targets at next open; missing exits wait for an actual bar.

    Random paths sample the same number of names from the same gated universe.
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


def run(panel, configs, output, random_paths):
    output.mkdir(parents=True, exist_ok=True)
    rows = []; paths = []
    for spec in configs:
        panel.ranking_frame(spec).to_csv(output / f"{spec.name}_weekly_ranks.csv", index=False)
        for window, (start, end) in WINDOWS.items():
            for fees, cost in COSTS.items():
                curve, fills, orders, gaps = simulate(panel, spec, start, end, cost)
                tag = f"{spec.name}_{window}_{fees}"
                curve.to_csv(output / f"{tag}_curve.csv")
                fills.to_csv(output / f"{tag}_fills.csv", index=False)
                orders.to_csv(output / f"{tag}_orders.csv", index=False)
                b = panel.benchmark.loc[curve.index]
                # Both XIU and portfolio finish at marked equity, without exit fees.
                bh = b.adj_close / (b.open.iloc[0] * b.adj_close.iloc[0] / b.close.iloc[0]) / (1 + cost)
                bh.to_csv(output / f"{tag}_XIU.csv")
                ends = []
                for seed in range(1000, 1000 + random_paths):
                    rc, rf, _, rg = simulate(panel, spec, start, end, cost, seed)
                    rm = metrics(rc); ends.append(rm["end_value"])
                    paths.append(dict(config=spec.name, window=window, fees=fees, seed=seed,
                                      fills=len(rf), entries=int(rf.opened_position.sum()),
                                      exits=int(rf.closed_position.sum()), **rm, **rg))
                sm = metrics(curve); bm = metrics(bh)
                rows.append(dict(config=spec.name, window=window, fees=fees,
                                 buys=int((fills.side == "buy").sum()), sells=int((fills.side == "sell").sum()),
                                 entries=int(fills.opened_position.sum()), exits=int(fills.closed_position.sum()),
                                 **sm, **gaps, xiu_cagr=bm["cagr"], xiu_max_dd=bm["max_dd"],
                                 random_end_mean=float(np.mean(ends)), random_end_p05=float(np.quantile(ends, .05)),
                                 random_end_p95=float(np.quantile(ends, .95)),
                                 selection_tail_fraction=(1 + sum(e >= sm["end_value"] for e in ends)) / (1 + len(ends))))
                print(tag, "buys", rows[-1]["buys"], "gaps", gaps, flush=True)
    pd.DataFrame(rows).to_csv(output / "summary.csv", index=False)
    pd.DataFrame(paths).to_csv(output / "random_paths.csv", index=False)
    manifest = dict(configs={s.name: asdict(s) for s in configs}, named={n: s.name for n, s in NAMED.items()},
                    universe=panel.symbols, empty_symbols_skipped=panel.empty,
                    sectors=SECTORS, available_sector_etfs=sorted(panel.sw),
                    index_proxy_symbols=[s for s in panel.symbols if s not in SECTORS],
                    windows=WINDOWS, costs=COSTS, random_paths=random_paths,
                    warning="Current fixed universe: survivorship bias. Tail fractions are descriptive, not multiplicity-corrected tests.")
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--grid", action="store_true")
    parser.add_argument("--random-paths", type=int, default=100)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test(); return
    if args.random_paths < 2:
        parser.error("--random-paths must be >=2")
    from ..data import load
    from ..config import TSX60
    yahoo_symbol = lambda t: t + ".TO"
    missing = []

    def cached(s):
        try:
            return load(s)
        except (FileNotFoundError, pd.errors.EmptyDataError):
            missing.append(s)
            return pd.DataFrame()

    data = {yahoo_symbol(s): cached(yahoo_symbol(s)) for s in TSX60}
    sectors = {s: cached(s) for s in sorted(set(SECTORS.values()))}
    panel = Panel(data, cached("XIU.TO"), sectors)
    configs = specs() if args.grid else list(dict.fromkeys(NAMED.values()))
    output = args.output or Path(__file__).resolve().parents[2] / "results" / "ta2" / OUT
    run(panel, configs, output, args.random_paths)
    (output / "missing_files.json").write_text(json.dumps(missing), encoding="utf-8")


def self_test():
    idx = pd.bdate_range("1998-01-01", "2006-12-29")

    def frame(rate):
        c = 100 * np.exp(np.arange(len(idx)) * rate)
        return pd.DataFrame(dict(open=c*.999, close=c, adj_close=c), index=idx)

    benchmark = frame(.0001)
    data = {f"S{j}": frame(.0002 + j*.00005) for j in range(12)}
    data["RY.TO"] = frame(.001)
    data["EMPTY"] = pd.DataFrame()
    sector = {"XFN.TO": frame(.0003)}
    p = Panel(data, benchmark, sector); spec = Spec(13, .20)
    assert len(specs()) <= 150 and len({s.name for s in specs()}) == len(specs())
    schedule = p.schedule(spec)
    assert any("RY.TO" in chosen for _, chosen, _ in schedule.values())
    for n in (330, 811, 1400):
        cut = idx[n-1]
        pp = Panel({s: d.loc[:cut] for s, d in data.items()}, benchmark.loc[:cut],
                   {s: d.loc[:cut] for s, d in sector.items()})
        assert pp.schedule(spec) == {d: v for d, v in schedule.items() if d <= cut}
    a, f, o, g = simulate(p, spec, "1999-01-01", "2006-01-01", cost=0)
    assert len(f) > 100 and a.iloc[-1] > 1
    assert (o.date > o.signal_date).all()
    scaled = Panel({s: d*7 for s, d in data.items()}, benchmark*3, {s: d*9 for s, d in sector.items()})
    b, _, _, _ = simulate(scaled, spec, "1999-01-01", "2006-01-01", cost=0)
    np.testing.assert_allclose(a, b)
    r1 = simulate(p, spec, "1999-01-01", "2006-01-01", seed=7)[0]
    r2 = simulate(p, spec, "1999-01-01", "2006-01-01", seed=7)[0]
    np.testing.assert_array_equal(r1, r2)
    # Perturb future data: no earlier orders, fills, or marks may change.
    cut = pd.Timestamp("2003-06-16")
    changed = {s: d.copy() for s, d in data.items()}
    for d in changed.values():
        if not d.empty:
            d.loc[d.index > cut] *= .5
    b, bf, bo, _ = simulate(Panel(changed, benchmark, sector), spec, "1999-01-01", "2006-01-01", cost=0)
    np.testing.assert_allclose(a.loc[:cut], b.loc[:cut])
    pd.testing.assert_frame_equal(o[o.date <= cut], bo[bo.date <= cut])
    pd.testing.assert_frame_equal(f[f.date <= cut], bf[bf.date <= cut])
    # Gap after entry: keep mark, and defer dropped-name exit until actual open.
    first = min(d for d, (_, chosen, _) in schedule.items() if chosen)
    held = schedule[first][1][0]
    broken = {s: d.copy() for s, d in data.items()}
    gapdates = idx[(idx > first) & (idx < first + pd.Timedelta(days=30))]
    broken[held] = broken[held].drop(gapdates)
    gp = Panel(broken, benchmark, sector)
    _, gf, _, gg = simulate(gp, spec, str(first), "2006-01-01")
    assert gg["held_missing_marks"] > 0 and gg["deferred_exit_days"] > 0
    assert not gf[(gf.symbol == held) & gf.date.isin(gapdates)].size
    # Sector history cannot be invented before ETF inception.
    late = Panel(data, benchmark, {"XFN.TO": sector["XFN.TO"].loc["2004-01-01":]})
    assert all("RY.TO" not in c for d, (_, c, _) in late.schedule(spec).items() if d.year < 2004)
    # Closed-form cash/fees test and forced gap exit (no synthetic fills).
    flat = benchmark.copy(); flat.loc[:, :] = 100.
    fp = Panel({"A": flat}, flat, {})
    d0, d1, d2 = idx[100:103]
    fp.cache[spec.name] = {d0: (idx[99], ["A"], ["A"]), d1: (d0, [], [])}
    fc, ff, _, _ = simulate(fp, spec, str(d0), str(idx[110]), cost=.01)
    np.testing.assert_allclose(fc.iloc[0], 1 / 1.01)
    np.testing.assert_allclose(fc.iloc[1:], .99 / 1.01)
    assert list(ff.side) == ["buy", "sell"]
    fp.opens.loc[d1, "A"] = np.nan; fp.close.loc[d1, "A"] = np.nan
    fc, ff, _, fg = simulate(fp, spec, str(d0), str(idx[110]), cost=.01)
    assert ff.iloc[-1].date == d2 and fg["deferred_exit_days"] == 1
    np.testing.assert_allclose(fc.iloc[1], 1 / 1.01)
    # Monthly orders occur at the first observed session of the next month.
    for date, (signal, _, _) in p.schedule(Spec(13, .20, "monthly")).items():
        assert date.month != signal.month
        assert not any((idx < date) & (idx.to_period("M") == date.to_period("M")))
    print("PASS: 37 unique specs; weekly prefixes; next-open/monthly execution; exact fees; cash accounting; scale symmetry; seeded random; future perturbation; missing-bar marks/deferred exits; ETF inception")


if __name__ == "__main__":
    main()

TIER = "weak"
EVIDENCE = ("RS leaders beat random picks from the same stocks by +4..7%/yr (TSX IS 6.4% vs XIU 5.2%) but trail XIU OOS (5.0% vs 10.8%). Weak; US not built.")
