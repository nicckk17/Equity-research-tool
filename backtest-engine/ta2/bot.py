"""The daily trading routine. Same rules as the backtest, executed through a broker.

  python -m ta2 bot plan                      what it would do today (no orders sent, no broker needed: --broker stub)
  python -m ta2 bot plan --broker ibkr         same, but reads your real paper account (positions, equity)
  python -m ta2 bot run --submit               sync -> exits -> entries, orders actually sent to IB paper
  python -m ta2 bot sync                       reconcile broker vs ledger, record fills, update equity curve
  python -m ta2 bot report                     trade log, R so far, slippage vs the backtest's cost assumption
  python -m ta2 bot close-check                after the close: did any stop fill today?

Order of the morning run (after the TSX open, which is when sizing is honest):
  1. sync      broker positions + equity + fills; the ledger must agree or the run stops
  2. exits     for every managed position, ask the strategy's own exit recipe (same rules as engine.py)
  3. entries   yesterday's close signals, sized on today's actual price, with the protective stop attached
  4. log       orders, equity, and a per-trade record for the 100-trade review

Safety rails, all in ta2/config.py: paper account only (broker.py enforces), 0.33% risk per trade,
20% notional cap, max 30 open, max new entries per day, drawdown kill switch, stale-data refusal,
and positions the bot did not open are never touched.
"""
from __future__ import annotations
import argparse, json, math, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np, pandas as pd
from . import config as C, data as D, broker as B
from .indicators import atr, context
from .strategies import get

LIVE = C.DATA / "live2"
LEDGER_COLS = ["symbol", "strategy", "version", "qty", "entry_date", "entry_px", "stop", "signal_date",
               "signal_close", "signal_atr", "planned_entry", "planned_stop", "planned_qty", "entry_order", "stop_order"]
TRADE_COLS = LEDGER_COLS + ["exit_date", "exit_px", "exit_reason", "R", "slippage_pct", "held_days"]


# ------------------------------------------------------------------ sessions and data
def sessions(day=None, now=None):
    """(last completed TSX session, next session). Refuses a session that has not closed yet."""
    import exchange_calendars as xc
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    today = now.tz_convert("America/Toronto").date()
    d = pd.Timestamp(day or today).normalize()
    if d.date() > today:
        raise ValueError("future dates are not allowed")
    cal = xc.get_calendar("XTSE", start=d - pd.Timedelta(days=400), end=d + pd.Timedelta(days=40))
    s = cal.date_to_session(d, direction="previous")
    if cal.session_close(s) + pd.Timedelta(minutes=15) > now:
        if day is not None:
            raise ValueError(f"session {s.date()} has not closed yet (+15 min publication buffer)")
        s = cal.previous_session(s)
    return pd.Timestamp(s).tz_localize(None), pd.Timestamp(cal.next_session(s)).tz_localize(None)


def fetch_bars(symbols, expected, workers=6, pause=0.3):
    """Fresh daily bars from Yahoo (same source and cleaning as the backtest). Refuses stale/missing data."""
    out, errors, lock = {}, [], __import__("threading").Lock()
    nxt = [time.monotonic()]

    def job(s):
        with lock:
            w = max(0, nxt[0] - time.monotonic()); nxt[0] = time.monotonic() + pause
        time.sleep(w)
        return D.fetch_chart(s, range_="2y")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for s, f in [(s, pool.submit(job, s)) for s in symbols]:
            try:
                df = f.result()
                out[s] = df.set_index("date") if len(df) else df
            except Exception as ex:
                errors.append(f"{s}: {ex}")
    if errors:
        raise ConnectionError("data refresh failed, no orders: " + "; ".join(errors[:5]))
    stale = [s for s, df in out.items() if len(df) == 0 or df.index[-1].normalize() != expected]
    return out, stale


# ------------------------------------------------------------------ strategy questions, answered the engine's way
def version_of(key):
    mod = get(key)
    name = getattr(mod, "LIVE", None) or next(iter(mod.KEEP))
    return mod, name, mod.KEEP[name]


def signal_today(mod, v, df, expected):
    """The strategy's own signal table, filtered to this version, on the last bar only."""
    ctx = context(df)
    sg = mod.signals(df, ctx)
    if sg is None or len(sg) == 0:
        return None
    m = (sg.fam == v["fam"]) & sg.side.isin(v.get("sides", (1,)))
    for f in v["flags"]:
        m &= sg[f].astype(bool)
    sg = sg[m & (sg.t == len(df) - 1)]
    return None if sg.empty else sg.iloc[0]


def exit_due(mod, v, df, pos_row, expected):
    """Does this position's exit rule fire on the latest close? Returns a reason or None.
    Uses the SAME exit recipe the backtest used (ta2/engine.py keys), so live and test agree."""
    recipe = mod.EXITS[v["target"]]
    ctx = context(df)
    lines = mod.lines(df, ctx, v["fam"], 1) if hasattr(mod, "lines") else {}
    side = 1
    if recipe.get("state"):
        s = np.asarray(lines[recipe["state"]], float)
        if np.isfinite(s[-1]) and side * s[-1] < 0:
            return f"rule exit: {recipe['state']} < 0 at {df.index[-1]:%Y-%m-%d} close"
    if recipe.get("close_line"):
        line = np.asarray(lines[recipe["close_line"]], float)
        if np.isfinite(line[-1]) and side * (df.close.iloc[-1] - line[-1]) < 0:
            return f"rule exit: close below {recipe['close_line']}"
    held = df.loc[pd.Timestamp(pos_row.entry_date):]
    bars = max(len(held) - 1, 0)
    for k, label in (("time_bars", "time exit"), ("max_hold", "max hold")):
        n = recipe.get(k)
        if n and bars >= int(n):
            return f"{label}: {bars} bars held (limit {int(n)})"
    return None


def resting_target(mod, v, entry, risk):
    """Price-level exits that belong at the broker, not in a daily decision."""
    r = mod.EXITS[v["target"]]
    if r.get("target_R"):
        return round(entry + float(r["target_R"]) * risk, 2)
    return None


# ------------------------------------------------------------------ ledger
def read_csv(p, cols):
    if not Path(p).exists():
        return pd.DataFrame(columns=cols)
    df = pd.read_csv(p)
    for c in cols:
        if c not in df:
            df[c] = pd.NA
    return df[cols]


def write_csv(df, p):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(p) + ".tmp"); df.to_csv(tmp, index=False); tmp.replace(p)


class Bot:
    def __init__(self, broker, live_dir=LIVE, keys=("S53",), risk=C.RISK_PER_TRADE, max_open=C.MAX_OPEN,
                 cap=C.NOTIONAL_CAP, max_new=C.MAX_NEW_PER_DAY, kill_dd=C.KILL_DRAWDOWN, day=None,
                 allow_foreign=False, bars=None):
        self.bk = broker; self.dir = Path(live_dir); self.keys = list(keys)
        self.risk, self.max_open, self.cap, self.max_new, self.kill_dd = risk, max_open, cap, max_new, kill_dd
        self.allow_foreign = allow_foreign
        self.bars = bars            # dict symbol -> bars; set for tests / offline dry runs instead of fetching
        self.expected, self.execution = sessions(day)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.ledger = read_csv(self.dir / "ledger.csv", LEDGER_COLS)
        self.trades = read_csv(self.dir / "trades.csv", TRADE_COLS)
        self.equity_log = read_csv(self.dir / "equity.csv", ["date", "equity", "currency", "fx_cad", "open_positions", "peak", "drawdown"])
        self.notes = []

    # -- 1 sync
    def sync(self):
        eq, cur = self.bk.equity()
        fx = 1.0 if cur == "CAD" else self._fx(cur)
        pos = {p.symbol: p for p in self.bk.positions()}
        managed = set(self.ledger.symbol)
        foreign = sorted(set(pos) - managed)
        if foreign:
            self.notes.append(f"{len(foreign)} position(s) this bot did not open and will not touch: {', '.join(foreign)}")
            if not self.allow_foreign:
                raise PermissionError(
                    "the account holds positions the bot did not open: " + ", ".join(foreign) +
                    ". Use an empty paper account, or pass --allow-foreign to leave them alone and trade around them.")
        closed = []
        for r in self.ledger.itertuples():
            held = pos.get(r.symbol)
            if held is None or abs(held.qty) < 1e-9:
                closed.append(r.symbol)
        for sym in closed:
            self._record_exit(sym, reason="gone from account (stop filled or sold elsewhere)")
        for r in self.ledger.itertuples():                       # quantity drift (partial fills)
            held = pos.get(r.symbol)
            if held is not None and abs(held.qty - float(r.qty)) > 1e-6:
                self.notes.append(f"{r.symbol}: broker has {held.qty:g} shares, ledger {float(r.qty):g} -> ledger updated")
                self.ledger.loc[self.ledger.symbol == r.symbol, "qty"] = held.qty
        peak = max([eq * fx] + [float(x) for x in self.equity_log.peak.dropna()] or [eq * fx])
        dd = eq * fx / peak - 1
        self.equity_log = pd.concat([self.equity_log[self.equity_log.date != str(self.execution.date())],
                                     pd.DataFrame([dict(date=str(self.execution.date()), equity=eq, currency=cur, fx_cad=fx,
                                                        open_positions=len(self.ledger), peak=peak, drawdown=round(dd, 4))])],
                                    ignore_index=True)
        self.eq_cad, self.fx, self.dd = eq * fx, fx, dd
        self.save()
        return dict(account=self.bk.account_id(), equity=eq, currency=cur, equity_cad=eq * fx,
                    open_positions=len(self.ledger), drawdown=round(dd, 4), foreign=foreign)

    def _fx(self, cur):
        if cur == "USD":
            fx = D.fetch_chart("CAD=X", range_="5d")
            if fx.empty:
                raise ConnectionError("no USDCAD rate; cannot size CAD positions from a USD account")
            return float(fx.close.iloc[-1])
        raise ValueError(f"account currency {cur}: add an FX pair for it before trading")

    def _record_exit(self, symbol, reason, exit_px=None, exit_date=None):
        row = self.ledger[self.ledger.symbol == symbol]
        if row.empty:
            return
        r = row.iloc[0].to_dict()
        fills = [f for f in self.bk.fills(since=pd.Timestamp(r["entry_date"])) if f.symbol == symbol and f.side == "SELL"]
        if exit_px is None and fills:
            exit_px = fills[-1].price; exit_date = fills[-1].time.normalize()
        px = float(exit_px) if exit_px is not None else np.nan
        risk = float(r["entry_px"]) - float(r["stop"])
        r.update(exit_date=str(pd.Timestamp(exit_date).date()) if exit_date is not None else "",
                 exit_px=px, exit_reason=reason,
                 R=round((px - float(r["entry_px"])) / risk, 4) if risk > 0 and np.isfinite(px) else np.nan,
                 slippage_pct=round((float(r["entry_px"]) / float(r["planned_entry"]) - 1) * 100, 4) if r.get("planned_entry") else np.nan,
                 held_days=(pd.Timestamp(exit_date) - pd.Timestamp(r["entry_date"])).days if exit_date is not None else np.nan)
        self.trades = pd.concat([self.trades, pd.DataFrame([r])[TRADE_COLS], ], ignore_index=True)
        self.ledger = self.ledger[self.ledger.symbol != symbol]
        self.notes.append(f"{symbol}: closed, {reason}" + (f", R {r['R']:+.2f}" if np.isfinite(r.get('R', np.nan)) else ""))

    def save(self):
        write_csv(self.ledger, self.dir / "ledger.csv")
        write_csv(self.trades, self.dir / "trades.csv")
        write_csv(self.equity_log, self.dir / "equity.csv")

    # -- 2+3 decide
    def plan(self):
        if not hasattr(self, "eq_cad"):
            self.sync()
        universe = sorted(set(s + ".TO" for s in C.TSX60) - set(C.DELISTED) | set(self.ledger.symbol))
        if self.bars is not None:
            bars = self.bars; stale = [s for s, d in bars.items() if len(d) == 0 or d.index[-1].normalize() != self.expected]
            universe = sorted(set(bars) | set(self.ledger.symbol))
        else:
            bars, stale = fetch_bars(universe, self.expected)
        if stale:
            held_stale = [s for s in stale if s in set(self.ledger.symbol)]
            if held_stale:
                raise ConnectionError(f"stale data for held position(s) {held_stale}: no orders written")
            self.notes.append(f"{len(stale)} symbol(s) with stale/empty data skipped: {', '.join(stale[:8])}")
        killed = self.dd <= -abs(self.kill_dd)
        if killed:
            self.notes.append(f"KILL SWITCH: drawdown {self.dd:.1%} past the {-abs(self.kill_dd):.0%} limit -> exits only, no new entries")
        exits, entries = [], []
        for key in self.keys:
            mod, vname, v = version_of(key)
            for r in self.ledger[self.ledger.strategy == key].itertuples():
                df = bars.get(r.symbol)
                if df is None or df.empty:
                    continue
                why = exit_due(mod, v, df, r, self.expected)
                if why:
                    exits.append(dict(symbol=r.symbol, strategy=key, qty=float(r.qty), reason=why))
            if killed:
                continue
            for sym in universe:
                if sym in set(self.ledger.symbol) or sym in stale:
                    continue
                df = bars.get(sym)
                if df is None or len(df) < C.MIN_BARS:
                    continue
                s = signal_today(mod, v, df, self.expected)
                if s is None:
                    continue
                close = float(df.close.iloc[-1])
                planned_stop = float(s.anchor) - float(v["buf"]) * float(s.A)
                if planned_stop <= 0 or close - planned_stop < C.MIN_R_ATR * float(s.A):
                    self.notes.append(f"{sym}: signal skipped, planned risk under {C.MIN_R_ATR} ATR")
                    continue
                entries.append(dict(symbol=sym, strategy=key, version=vname, signal_date=str(self.expected.date()),
                                    signal_close=close, signal_atr=float(s.A), anchor=float(s.anchor), buf=float(v["buf"]),
                                    planned_entry=close, planned_stop=round(planned_stop, 2),
                                    atr_pct=float(s.A) / close, target=resting_target(mod, v, close, close - planned_stop)))
        slots = max(0, self.max_open - len(self.ledger) - len(exits) * 0)      # a SELL frees a slot only once filled
        entries.sort(key=lambda e: (e["atr_pct"], e["symbol"]))                # lowest volatility first (tested rule)
        if len(entries) > min(slots, self.max_new):
            self.notes.append(f"{len(entries) - min(slots, self.max_new)} signal(s) not taken: "
                              f"{len(self.ledger)}/{self.max_open} slots used, max {self.max_new} new per day")
        entries = entries[:min(slots, self.max_new)]
        self.plan_exits, self.plan_entries = exits, entries
        return exits, entries

    # -- sizing at the real price
    def size(self, e, price):
        stop = e["planned_stop"]
        risk = price - stop
        if risk < C.MIN_R_ATR * e["signal_atr"]:
            return 0, f"risk {risk:.2f} under {C.MIN_R_ATR} ATR at {price:.2f}"
        qty = math.floor(min(self.risk * self.eq_cad / risk, self.cap * self.eq_cad / price))
        if qty < 1:
            return 0, f"size rounds to 0 (risk budget CAD {self.risk * self.eq_cad:,.0f})"
        return qty, ""

    # -- 4 execute
    def run(self, submit=False):
        exits, entries = self.plan()
        done = []
        for x in exits:
            if submit:
                res = self.bk.place_exit(x["symbol"], x["qty"], ref=f"{x['strategy']}|exit")
                self._record_exit(x["symbol"], x["reason"], exit_px=self._last_fill(x["symbol"], "SELL"),
                                  exit_date=self.execution)
                done.append({**x, **res})
            else:
                done.append(dict(x, status="PLAN"))
        for e in entries:
            try:
                price = self.bk.price(e["symbol"]) if submit or self.bk.name == "stub" else e["planned_entry"]
            except Exception as ex:
                self.notes.append(f"{e['symbol']}: no live price ({ex}); skipped"); continue
            qty, why = self.size(e, price)
            if qty == 0:
                self.notes.append(f"{e['symbol']}: {why}"); continue
            if not submit:
                done.append(dict(e, action="BUY", qty=qty, price=price, status="PLAN")); continue
            res = self.bk.place_entry(e["symbol"], qty, e["planned_stop"], ref=f"{e['strategy']}|entry")
            fill = self._last_fill(e["symbol"], "BUY") or price
            self.ledger = pd.concat([self.ledger, pd.DataFrame([dict(
                symbol=e["symbol"], strategy=e["strategy"], version=e["version"], qty=qty,
                entry_date=str(self.execution.date()), entry_px=fill, stop=e["planned_stop"],
                signal_date=e["signal_date"], signal_close=e["signal_close"], signal_atr=e["signal_atr"],
                planned_entry=e["planned_entry"], planned_stop=e["planned_stop"], planned_qty=qty,
                entry_order=res.get("entry_order"), stop_order=res.get("stop_order"))])[LEDGER_COLS]],
                ignore_index=True)
            done.append({**e, **res, "action": "BUY", "qty": qty, "price": fill})
        self.save()
        self.write_report(done, submitted=submit)
        return done

    def _last_fill(self, symbol, side):
        f = [x for x in self.bk.fills(since=self.expected) if x.symbol == symbol and x.side == side]
        return f[-1].price if f else None

    def write_report(self, done, submitted):
        label = str(self.execution.date())
        df = pd.DataFrame(done)
        write_csv(df, self.dir / f"orders_{label}.csv")
        md = [f"# {'Orders sent' if submitted else 'PLAN (nothing sent)'} - {label}",
              f"Signals from the {self.expected:%Y-%m-%d} close. Account {self.bk.account_id()} "
              f"({self.bk.name}{', paper' if getattr(self.bk, 'is_paper', lambda: False)() else ''}), "
              f"equity CAD {self.eq_cad:,.0f}, drawdown {self.dd:.1%}, {len(self.ledger)}/{self.max_open} slots used.",
              f"Risk {self.risk:.2%} of equity per trade = CAD {self.risk * self.eq_cad:,.0f}; "
              f"max {self.cap:.0%} of equity per position; kill switch at {-abs(self.kill_dd):.0%}.", ""]
        if len(df):
            cols = [c for c in ("action", "symbol", "qty", "price", "planned_stop", "stop", "reason", "status") if c in df]
            md += [df[cols].to_markdown(index=False), ""]
        else:
            md += ["Nothing to do today.", ""]
        md += [f"- {n}" for n in self.notes]
        (self.dir / f"orders_{label}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
        print("\n".join(md))

    # -- reporting
    def report(self):
        t = self.trades.copy()
        n = len(t)
        out = [f"Account {self.bk.account_id()} ({self.bk.name}); {len(self.ledger)} open, {n} closed trades."]
        if n:
            R = pd.to_numeric(t.R, errors="coerce").dropna()
            out += [f"Closed R: total {R.sum():+.1f}, average {R.mean():+.3f}, win rate {100 * (R > 0).mean():.1f}% "
                    f"(backtest: average +0.10 to +0.20R, win about 40%).",
                    f"Average entry slippage vs the signal close: {pd.to_numeric(t.slippage_pct, errors='coerce').mean():+.3f}% "
                    f"(backtest assumes {C.COST_MAIN:.2%} per side).",
                    f"Median days held: {pd.to_numeric(t.held_days, errors='coerce').median():.0f} (backtest about 21).",
                    ("REVIEW DUE: 100 closed trades reached." if n >= 100 else f"{100 - n} trades to the 100-trade review.")]
        if len(self.equity_log):
            e = self.equity_log.iloc[-1]
            out.append(f"Equity {float(e.equity):,.2f} {e.currency}; peak-to-now {float(e.drawdown):.1%}; "
                       f"kill switch at {-abs(self.kill_dd):.0%}.")
        if len(self.ledger):
            out.append("\nOpen: " + ", ".join(f"{r.symbol} {float(r.qty):g}@{float(r.entry_px):.2f} stop {float(r.stop):.2f}"
                                               for r in self.ledger.itertuples()))
        print("\n".join(out))
        return out


def build(a):
    kw = dict(live_dir=a.dir or LIVE, keys=a.strategies.split(","), day=a.date, allow_foreign=a.allow_foreign)
    if a.broker == "stub":
        bk = B.StubBroker(prices={}).connect()
        if a.stub_prices:
            bk.prices = json.loads(Path(a.stub_prices).read_text())
    else:
        bk = B.IBKRBroker(host=a.host, port=a.port, client_id=a.client_id, account=a.account,
                          cache=(a.dir or LIVE) / "ib_contracts.json").connect()
    return Bot(bk, **kw)


def main(argv=None):
    p = argparse.ArgumentParser(prog="ta2 bot", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("action", choices=["plan", "run", "sync", "report", "close-check"])
    p.add_argument("--broker", default="ibkr", choices=["ibkr", "stub"])
    p.add_argument("--submit", action="store_true", help="actually send orders (run only); without it, plan only")
    p.add_argument("--strategies", default="S53")
    p.add_argument("--host", default="127.0.0.1"); p.add_argument("--port", type=int, default=4002)
    p.add_argument("--client-id", type=int, default=17); p.add_argument("--account", default="")
    p.add_argument("--date"); p.add_argument("--dir", type=Path); p.add_argument("--stub-prices")
    p.add_argument("--allow-foreign", action="store_true", help="account holds positions the bot did not open: leave them alone")
    a = p.parse_args(argv)
    bot = build(a)
    try:
        if a.action == "sync":
            print(json.dumps(bot.sync(), indent=2, default=str)); [print("-", n) for n in bot.notes]
        elif a.action == "plan":
            bot.run(submit=False)
        elif a.action == "run":
            if not a.submit:
                print("No --submit: planning only.\n")
            bot.run(submit=a.submit)
        elif a.action == "close-check":
            print(json.dumps(bot.sync(), indent=2, default=str)); [print("-", n) for n in bot.notes]; bot.report()
        else:
            bot.sync(); bot.report()
    finally:
        bot.bk.disconnect()
