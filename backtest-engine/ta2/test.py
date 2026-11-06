"""The honest test. One command runs every check v1 used:

  python -m ta2 test S53                 # build -> grid -> bootstrap -> report -> named/keep -> edge  (TSX)
  python -m ta2 test S53 --universe US   # US cold check
  python -m ta2 test S53 --holdout       # adds the spent holdout window (HO) - report only, never choose on it
  python -m ta2 test S53 --steps build   # one step: build | grid | boot | report | named | edge
  python -m ta2 test S53 --chunk 3       # build one chunk only (for the 3-minute limit on Claude's PC calls)

Pipeline:
 1 build : signals for every stock -> trades for every exit x entry mode x stop buffer, each with 5 random twins.
           Resumable: chunks already on disk are skipped.
 2 grid  : every config (filters x exit x side x entry x buffer) in every window, at main and low fees.
 3 boot  : week-block bootstrap; Romano-Wolf luck correction across all configs.
 4 report: the funnel (>=100 trades -> profitable -> beats random -> survives luck IS -> holds OOS) + dial effects.
 5 named : the as-taught / as-traded / KEEP versions, a ladder, and a daily portfolio vs XIU.
 6 edge  : "true edge" per KEEP version: trades/yr, R/yr, drift vs skill R/yr (p), % vs index over the same days.
"""
from __future__ import annotations
import argparse, itertools, pickle, time
import numpy as np, pandas as pd
from . import config as C, data as D, engine as E
from .indicators import context
from .strategies import get

ENTRY = {0: "close", 1: "next_open", 2: "open", 3: "order"}


class Run:
    def __init__(self, key, universe="TSX", holdout=False):
        self.mod = get(key); self.key = key.upper(); self.universe = universe; self.holdout = holdout
        self.u = C.UNIVERSES[universe]; self.syms = self.u["symbols"]
        self.windows = {"IS": C.IS, "OOS": C.OOS} | ({"HO": C.HOLDOUT} if holdout else {})
        self.out = C.RESULTS / (self.key + ("_US" if universe == "US" else "") + ("_HO" if holdout else ""))
        self.out.mkdir(parents=True, exist_ok=True)

    def sides(self):
        return getattr(self.mod, "SIDES", (1, -1))

    def tcode(self, target):
        return list(self.mod.TARGETS).index(target)

    # ------------------------------------------------------------ 1 build
    def chunks(self):
        cs = getattr(self.mod, "CHUNK", 10)
        return [list(range(i, min(i + cs, len(self.syms)))) for i in range(0, len(self.syms), cs)]

    def build(self, only=None):
        for ci, codes in enumerate(self.chunks()):
            if (only is not None and ci != only) or (only is None and (self.out / f"res_{ci}.pkl").exists()):
                continue
            self._build_chunk(ci, codes)

    def _build_chunk(self, ci, codes):
        t0 = time.time(); mod = self.mod; sig_all, res_all = [], []
        for code in codes:
            sym = self.syms[code]
            df = D.load(sym, self.universe, self.holdout)
            if len(df) < C.MIN_BARS:
                continue
            ctx = context(df, D.earnings(sym, self.universe))
            ctx["universe"] = self.universe
            sg = mod.signals(df, ctx)
            if sg is None or len(sg) == 0:
                continue
            sg = sg[(sg.t >= 1) & (sg.t < len(df) - 1) & np.isfinite(sg.A) & (sg.A > 0)].reset_index(drop=True)
            win, lo, hi = self._bounds(df.index, sg.t.to_numpy())
            sg["window"], sg["lo"], sg["hi"] = win, lo, hi
            sg = sg[sg.window != ""].reset_index(drop=True)
            if len(sg) == 0:
                continue
            sg["sym"] = sym.replace(".TO", ""); sg["sym_code"] = code
            sg["date"] = df.index[sg.t.to_numpy()]; sg["sig_id"] = code * 1_000_000 + np.arange(len(sg))
            days = df.index.values.astype("datetime64[D]").astype(np.int64)
            groups = {k: g for k, g in sg.groupby(["fam", "side"], sort=True)}
            for (fam, side), g in groups.items():
                lines = mod.lines(df, ctx, fam, side) if hasattr(mod, "lines") else {}
                for mode, (bi, buf), tg in itertools.product(mod.MODES, enumerate(mod.BUFS), mod.TARGETS):
                    seed = code * 100 + mode * 10 + int(buf * 10)
                    r = E.trades(df, ctx, g, mode, buf, mod.EXITS[tg], lines, seed)
                    v = r.valid.to_numpy(); r = r[v]
                    if not len(r):
                        continue
                    res_all.append(pd.DataFrame(dict(
                        sig_id=g.sig_id.to_numpy()[v], mode=np.int8(mode), bi=np.int8(bi), tc=np.int8(self.tcode(tg)),
                        e=r.e.to_numpy(np.int32), xb=r.exit_bar.to_numpy(np.int32),
                        ed=days[r.e.to_numpy()].astype(np.int32), xd=days[r.exit_bar.to_numpy()].astype(np.int32),
                        entry=r.entry.to_numpy(np.float32), R=r.R.to_numpy(np.float32),
                        exit_px=r.exit_px.to_numpy(np.float32), reason=r.reason.to_numpy(np.int8),
                        **{k: r[k].to_numpy(np.float32) for k in ("gR", "kC", "kS", "kB", "rgR", "rkC", "rkS", "rkB")})))
            sig_all.append(sg.drop(columns=["lo", "hi"]))
            print(f"  {sym}: {len(sg)} signals, {time.time() - t0:.0f}s", flush=True)
        S = pd.concat(sig_all, ignore_index=True) if sig_all else pd.DataFrame()
        R = pd.concat(res_all, ignore_index=True) if res_all else pd.DataFrame()
        S.to_pickle(self.out / f"sig_{ci}.pkl"); R.to_pickle(self.out / f"res_{ci}.pkl")
        print(f"chunk {ci}: {len(S)} signals, {len(R)} trades, {time.time() - t0:.0f}s", flush=True)

    def _bounds(self, dates, t):
        win = np.full(len(t), "", dtype=object); lo = np.zeros(len(t), np.int64); hi = np.zeros(len(t), np.int64)
        d = dates[t]
        for w, (a, z) in self.windows.items():
            m = (d >= pd.Timestamp(a)) & (d <= pd.Timestamp(z))
            win[m] = w; lo[m] = dates.searchsorted(pd.Timestamp(a)); hi[m] = dates.searchsorted(pd.Timestamp(z), side="right")
        return win, lo, hi

    def load_all(self):
        fs = sorted(self.out.glob("sig_*.pkl"))
        S = pd.concat([pd.read_pickle(f) for f in fs if f.stat().st_size > 0], ignore_index=True)
        R = pd.concat([pd.read_pickle(f) for f in sorted(self.out.glob("res_*.pkl"))], ignore_index=True)
        R["si"] = pd.Index(S.sig_id).get_indexer(R.sig_id).astype(np.int64)
        return S, R

    # ------------------------------------------------------------ book: a config = flag mask + one position per stock
    def book(self):
        S, R = self.load_all(); self.S = S
        self.famcat = pd.Categorical(S.fam); self.famcode = {f: i for i, f in enumerate(self.famcat.categories)}
        self.fam = self.famcat.codes; self.F = {f: S[f].to_numpy(bool) for f in self.mod.FLAGS}
        R["symc"] = S.sym_code.to_numpy()[R.si.to_numpy()]
        R["side"] = S.side.to_numpy()[R.si.to_numpy()].astype(np.int8)
        wmap = {w: i for i, w in enumerate(self.windows)}
        R["w"] = pd.Series(S.window.to_numpy()[R.si.to_numpy()]).map(wmap).to_numpy(np.int8)
        R.sort_values(["symc", "e"], inplace=True, kind="stable")
        cols = ("si", "symc", "e", "xb", "ed", "xd", "entry", "R", "exit_px", "reason",
                "gR", "kC", "kS", "kB", "rgR", "rkC", "rkS", "rkB")
        self.G = {tuple(int(x) for x in k): {c: g[c].to_numpy() for c in cols}
                  for k, g in R.groupby(["tc", "mode", "bi", "side", "w"], sort=False)}
        self.cols = cols; self.wmap = wmap
        return self

    def select(self, fam, flags, target, side, mode, buf, window):
        g = self.G.get((self.tcode(target), mode, list(self.mod.BUFS).index(buf), side, self.wmap[window]))
        if g is None or fam not in self.famcode:
            return {c: np.array([]) for c in self.cols}
        si = g["si"]; m = self.fam[si] == self.famcode[fam]
        for f in flags:
            m &= self.F[f][si]
        idx = np.nonzero(m)[0]
        idx = idx[E.nonoverlap(g["symc"][idx].astype(np.int64), g["e"][idx].astype(np.int64), g["xb"][idx].astype(np.int64))]
        return {c: g[c][idx] for c in self.cols}

    def configs(self):
        return [dict(dials=d, fam=f, flags=tuple(fl), target=tg, side=sd, mode=md, buf=bf)
                for d, f, fl in self.mod.specs()
                for tg, sd, md, bf in itertools.product(self.mod.TARGETS, self.sides(), self.mod.MODES, self.mod.BUFS)]

    @staticmethod
    def cname(c):
        return "|".join(f"{k}={v}" for k, v in c["dials"].items()) + \
            f"|{c['target']}|{'L' if c['side'] == 1 else 'S'}|{ENTRY[c['mode']]}|buf{c['buf']}"

    # ------------------------------------------------------------ 2 grid + 3 boot
    def grid_boot(self):
        t0 = time.time(); self.book(); Cs = self.configs(); rows = []
        per = {(w, cl): [] for w in self.windows for cl in ("main", "low")}
        for i, c in enumerate(Cs):
            for w in self.windows:
                x = self.select(c["fam"], c["flags"], c["target"], c["side"], c["mode"], c["buf"], w)
                wk = (x["ed"].astype(np.int64) + 3) // 7
                for cl, cost in (("main", C.COST_MAIN), ("low", C.COST_LOW)):
                    rn, rr = E.r_net(x, cost)
                    rows.append(dict(ci=i, name=self.cname(c), window=w, cost=cl, **{("dial_" + k): v for k, v in c["dials"].items()},
                                     target=c["target"], side=c["side"], entry=ENTRY[c["mode"]], buf=c["buf"], **E.stats(rn, rr, x["ed"])))
                    ok = np.isfinite(rr); per[(w, cl)].append((i, wk[ok], (rn - rr)[ok]))
        G = pd.DataFrame(rows); res = []
        for w in self.windows:
            allw = np.unique(np.concatenate([wk for (_, wk, _) in per[(w, "main")]] + [np.array([], np.int64)]))
            widx = {x: j for j, x in enumerate(allw)}
            for cl in ("main", "low"):
                Sm = np.zeros((len(Cs), max(len(widx), 1))); Nm = np.zeros_like(Sm)
                for i, wk, v in per[(w, cl)]:
                    if len(wk):
                        j = np.array([widx[x] for x in wk]); np.add.at(Sm[i], j, v); np.add.at(Nm[i], j, 1)
                enough = Nm.sum(1) >= C.MIN_TRADES[w]
                mean, se, ts, p1, prw = E.block_boot(np.where(enough[:, None], Sm, 0), np.where(enough[:, None], Nm, 0))
                res.append(pd.DataFrame(dict(ci=np.arange(len(Cs)), window=w, cost=cl, boot_edge=mean, boot_se=se,
                                             p_single=np.where(enough, p1, np.nan), p_rw=np.where(enough, prw, np.nan))))
        G = G.merge(pd.concat(res), on=["ci", "window", "cost"]); G.to_pickle(self.out / "grid_boot.pkl")
        print(f"grid+boot: {len(Cs)} configs, {time.time() - t0:.0f}s")

    # ------------------------------------------------------------ 4 report
    def report(self):
        G = pd.read_pickle(self.out / "grid_boot.pkl"); lines = []
        for cl in ("main", "low"):
            W = G[G.cost == cl].pivot_table(index="name", columns="window",
                                            values=["n", "avgR", "PF", "edge", "win", "p_single", "p_rw"], aggfunc="first")
            W.columns = [f"{a}_{b}" for a, b in W.columns]; W = W.reset_index()
            for col in ("p_rw_IS", "p_single_OOS", "n_OOS", "avgR_OOS", "edge_OOS", "n_IS", "avgR_IS", "edge_IS"):
                if col not in W:
                    W[col] = np.nan
            f1 = W[W.n_IS >= C.MIN_TRADES["IS"]]; f2 = f1[f1.avgR_IS > 0]; f3 = f2[f2.edge_IS > 0]
            f5 = f3[f3.p_rw_IS < C.P_PASS]
            f6 = f5[(f5.n_OOS >= C.MIN_TRADES["OOS"]) & (f5.avgR_OOS > 0) & (f5.edge_OOS > 0) & (f5.p_single_OOS < C.P_PASS)]
            F = pd.DataFrame([("configs tested", len(W)), (f">={C.MIN_TRADES['IS']} trades IS", len(f1)),
                              ("profitable after costs IS", len(f2)), ("beats random entry IS", len(f3)),
                              ("survives luck correction (Romano-Wolf) IS", len(f5)), ("holds OOS 2016-2024", len(f6))],
                             columns=["step", f"configs ({cl} fees)"])
            W.sort_values("edge_IS", ascending=False).to_csv(self.out / f"grid_{cl}.csv", index=False)
            F.to_csv(self.out / f"funnel_{cl}.csv", index=False)
            lines += [F.to_string(index=False), ""]
            if len(f3):
                lines += [f"Best 15 configs that beat random IS ({cl} fees), by luck-corrected p:",
                          f3.sort_values("p_rw_IS")[["name", "n_IS", "avgR_IS", "edge_IS", "p_rw_IS", "n_OOS", "avgR_OOS",
                                                      "edge_OOS", "p_single_OOS"]].head(15).round(3).to_string(index=False), ""]
            if cl == "main":
                verdict = "PASS" if len(f6) else "FAIL"
                lines.insert(0, f"VERDICT {self.key} ({self.universe}): {verdict} - {len(f6)} config(s) survive luck correction IS and hold OOS\n")
        (self.out / "report_grid.txt").write_text("\n".join(lines)); print("\n".join(lines))

    # ------------------------------------------------------------ 5 named + KEEP versions, ladder, portfolio
    def versions(self):
        v = dict(getattr(self.mod, "NAMED", {}))
        v.update({f"KEEP: {k}": x for k, x in getattr(self.mod, "KEEP", {}).items()})
        return v

    def named(self):
        t0 = time.time(); self.book()
        closes = D.closes(self.universe, self.holdout); bench = D.load(self.u["bench"], self.universe, self.holdout).adj_close
        rows, prow = [], []
        for w, (a, b) in self.windows.items():
            prow.append(dict(version=f"{self.u['bench']} buy-and-hold", window=w, **{k: v for k, v in E.buy_hold(bench, a, b).items() if k != "curve"}))
        for nm, v in self.versions().items():
            for sd in v.get("sides", self.sides()):
                for w, (a, b) in self.windows.items():
                    x = self.select(v["fam"], tuple(v["flags"]), v["target"], sd, v["mode"], v["buf"], w)
                    for cl, cost in (("main", C.COST_MAIN), ("low", C.COST_LOW)):
                        rn, rr = E.r_net(x, cost)
                        rows.append(dict(version=nm, side="long" if sd == 1 else "short", window=w, fees=cl, **E.stats(rn, rr, x["ed"])))
                    tr = self.to_trades(x, sd)
                    p = {k: v2 for k, v2 in E.portfolio(tr, closes, a, b).items() if k != "curve"} if len(tr) else dict(taken=0)
                    prow.append(dict(version=f"{nm} {'long' if sd == 1 else 'short'}", window=w, **p))
        Nm, P = pd.DataFrame(rows), pd.DataFrame(prow)
        Nm.to_csv(self.out / "named_versions.csv", index=False); P.to_csv(self.out / "portfolio.csv", index=False)
        L = []
        lad = getattr(self.mod, "LADDER", None)
        if lad:
            base = lad["base"]
            for sd in self.sides():
                cum = dict(base, flags=list(base["flags"]))
                for lab, ch, is_cum in lad["steps"]:
                    alone = dict(base, flags=list(base["flags"]))
                    for tgt in ([cum] if is_cum else []) + [alone]:
                        if "add" in ch: tgt["flags"] = tgt["flags"] + [ch["add"]]
                        if "fam" in ch: tgt["fam"] = ch["fam"]
                        if "target" in ch: tgt["target"] = ch["target"]
                    for mlab, cfg in (("cumulative", cum if is_cum else None), ("alone", alone)):
                        if cfg is None:
                            continue
                        for w in self.windows:
                            x = self.select(cfg["fam"], tuple(cfg["flags"]), cfg["target"], sd, cfg["mode"], cfg["buf"], w)
                            rn, rr = E.r_net(x, C.COST_MAIN)
                            L.append(dict(side="long" if sd == 1 else "short", mode=mlab, step=lab, window=w, **E.stats(rn, rr, x["ed"])))
        L = pd.DataFrame(L); L.to_csv(self.out / "ladder.csv", index=False)
        pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30); pd.set_option("display.max_colwidth", 70)
        txt = ["Named + KEEP versions:", Nm.to_string(index=False), "",
               f"Portfolio (daily mark-to-market, {C.RISK_PER_TRADE:.2%} risk/trade, max {C.MAX_OPEN} open):", P.to_string(index=False),
               "", "Ladder (main fees):", L.to_string(index=False)]
        (self.out / "report_named.txt").write_text("\n".join(txt)); print("\n".join(txt[:5])); print(f"{time.time() - t0:.0f}s")

    def to_trades(self, x, side):
        if len(x["si"]) == 0:
            return pd.DataFrame(columns=["sym", "side", "entry_date", "exit_date", "entry", "exit_px", "R", "reason"])
        return pd.DataFrame(dict(sym=self.S.sym.to_numpy()[x["si"]], side=side,
                                 entry_date=pd.to_datetime(x["ed"].astype("int64"), unit="D"),
                                 exit_date=pd.to_datetime(x["xd"].astype("int64"), unit="D"),
                                 entry=x["entry"].astype(float), exit_px=x["exit_px"].astype(float),
                                 R=x["R"].astype(float), reason=x["reason"].astype(int),
                                 atr_pct=self.S.A.to_numpy()[x["si"]] / x["entry"].astype(float)))

    # ------------------------------------------------------------ 6 true edge (every signal, $100 risk, no cap)
    def edge(self):
        self.book(); bench = D.load(self.u["bench"], self.universe, self.holdout).adj_close.dropna()
        cal = bench.index; rows = []
        for nm, v in getattr(self.mod, "KEEP", {}).items():
            for sd in v.get("sides", (1,)):
                for w, (a, b) in self.windows.items():
                    x = self.select(v["fam"], tuple(v["flags"]), v["target"], sd, v["mode"], v["buf"], w)
                    rows.append(dict(version=nm, side=sd, universe=self.universe, window=w, **edge_metrics(x, sd, a, b, bench, cal)))
        T = pd.DataFrame(rows); T.to_csv(self.out / "edge.csv", index=False)
        show = ["version", "window", "n", "trades_per_yr", "win_pct", "avgR", "total_R_yr", "drift_R_yr", "skill_R_yr", "p",
                "avg_open", "max_open", "excess_pct_per_yr_held"]
        pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 60)
        txt = T[[c for c in show if c in T]].round(3).to_string(index=False)
        (self.out / "report_edge.txt").write_text(txt); print(txt)


def edge_metrics(x, side, a, b, bench, cal):
    a, b = pd.Timestamp(a), pd.Timestamp(b); yrs = ((b - a).days + 1) / 365.25
    rn, rr = E.r_net(x, C.COST_MAIN); n = len(rn)
    if n == 0:
        return dict(n=0)
    ed = pd.to_datetime(x["ed"].astype("int64"), unit="D"); xd = pd.to_datetime(x["xd"].astype("int64"), unit="D")
    wcal = cal[(cal >= a) & (cal <= b)]
    s = wcal.searchsorted(ed); e2 = wcal.searchsorted(xd, side="right"); hold = np.maximum(e2 - s, 1)
    ch = np.zeros(len(wcal) + 1); np.add.at(ch, np.clip(s, 0, len(wcal)), 1); np.add.at(ch, np.clip(e2, 0, len(wcal)), -1)
    wk = (x["ed"].astype(np.int64) + 3) // 7; uw = {w: i for i, w in enumerate(np.unique(wk))}
    Sm = np.zeros((1, len(uw))); Nm = np.zeros((1, len(uw))); j = np.array([uw[w] for w in wk])
    np.add.at(Sm[0], j, rn - rr); np.add.at(Nm[0], j, 1)
    p = float(E.block_boot(Sm, Nm)[3][0])
    tp = side * (x["exit_px"].astype(float) / x["entry"].astype(float) - 1) - 2 * C.COST_MAIN
    b0 = bench.reindex(ed, method="ffill").to_numpy(); b1 = bench.reindex(xd, method="ffill").to_numpy()
    exc = tp - (b1 / b0 - 1); ok = np.isfinite(exc)
    return dict(n=n, trades_per_yr=n / yrs, win_pct=100 * float((rn > 0).mean()), avgR=float(rn.mean()),
                total_R_yr=float(rn.sum()) / yrs, drift_R_yr=float(np.nansum(rr)) / yrs,
                skill_R_yr=float(np.nansum(rn - rr)) / yrs, p=p, avg_open=float(hold.sum()) / max(len(wcal), 1),
                max_open=int(np.cumsum(ch[:-1]).max()), avg_hold_days=float(hold.mean()),
                excess_pct_per_yr_held=float(np.nansum(exc[ok]) / hold[ok].sum() * 252) * 100 if ok.any() else np.nan)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ta2 test")
    ap.add_argument("key"); ap.add_argument("--universe", default="TSX", choices=list(C.UNIVERSES))
    ap.add_argument("--holdout", action="store_true"); ap.add_argument("--chunk", type=int)
    ap.add_argument("--steps", default="build,grid,report,named,edge")
    a = ap.parse_args(argv); r = Run(a.key, a.universe, a.holdout); steps = a.steps.split(",")
    if "build" in steps:
        r.build(a.chunk)
        if a.chunk is not None:
            return
    if "grid" in steps or "boot" in steps:
        r.grid_boot()
    if "report" in steps:
        r.report()
    if "named" in steps:
        r.named()
    if "edge" in steps:
        r.edge()
