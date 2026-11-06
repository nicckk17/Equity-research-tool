"""Daily paper-trading scanner for S53 (survivor rules). Moved from v1 phase2/s53_live.py, logic unchanged.

No brokerage connection. Only fill records confirmed paper executions.
python -m ta2 live scan | fill BUY TSX:RY <qty> <price> <date> --stop X | status | self-test
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import math
from pathlib import Path
import tempfile
import threading
import time
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
import uuid

import numpy as np
import pandas as pd
from .strategies import s53_macd as S53
from .indicators import atr

ROOT = Path(__file__).resolve().parent.parent
LIVE = ROOT / "data" / "live"
BAR_COLS = ["open", "high", "low", "close", "adj_close", "volume"]
LEDGER_COLS = ["symbol", "entry_date", "qty", "entry_px", "stop", "status",
               "trade_id", "initial_qty", "exit_date", "exit_px"]
ORDER_COLS = ["action", "symbol", "tv_symbol", "qty", "entry_est_cad", "stop",
              "signal_date", "execute_date", "timing", "reason", "atr_pct",
              "equity_usd", "usdcad", "equity_cad", "risk_budget_cad"]


def symbol(value):
    value = value.upper().removeprefix("TSX:").removesuffix(".TO")
    if not value or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-" for c in value):
        raise ValueError("invalid TSX symbol")
    return value.replace(".", "-") + ".TO"


def tv_symbol(value):
    return "TSX:" + symbol(value).removesuffix(".TO").replace("-", ".")


from .config import DELISTED


def universe():
    from .config import TSX60
    yahoo_symbol = lambda t: t + ".TO"
    # Claude 2026-11-01: delisted names (verified) are dropped from the LIVE universe only.
    return sorted({yahoo_symbol(s) for s in TSX60} - set(DELISTED))


def read_bars(path):
    if not path.exists():
        return pd.DataFrame(columns=BAR_COLS, index=pd.DatetimeIndex([], name="date"))
    df = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    if not df.index.is_unique:
        raise ValueError(f"duplicate dates in {path}")
    return df


def atomic_csv(df, path, index=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, index=index)
    tmp.replace(path)


def calendar(day):
    import exchange_calendars as xc
    d = pd.Timestamp(day).normalize().tz_localize(None)
    return xc.get_calendar("XTSE", start=d - pd.Timedelta(days=400),
                           end=d + pd.Timedelta(days=40))


def session_dates(day=None, now=None):
    """Return latest completed TSX session and its next session (holidays included)."""
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if now.tzinfo is None:
        raise ValueError("now must have timezone")
    today = now.tz_convert("America/Toronto").date()
    d = pd.Timestamp(day or today).normalize()
    if d.date() > today:
        raise ValueError("future scan dates are not allowed")
    cal = calendar(d)
    s = cal.date_to_session(d, direction="previous")
    # Default during a session uses the previous completed session; an explicit
    # date refuses an incomplete session instead of silently relabeling it.
    if cal.session_close(s) + pd.Timedelta(minutes=15) > now:
        if day is not None:
            raise ValueError("requested session has not closed (+15-minute publication buffer)")
        s = cal.previous_session(s)
    return pd.Timestamp(s).tz_localize(None), pd.Timestamp(cal.next_session(s)).tz_localize(None)


def fresh(df, expected, name):
    if df.empty or df.index[-1].normalize() != expected:
        last = "empty" if df.empty else str(df.index[-1].date())
        raise ValueError(f"STALE DATA {name}: last={last}; expected={expected.date()}; no orders written")


def selected_signals(df):
    """Do not reimplement cross/episode/warmup/zero-line rules."""
    sg = S53.signals(df, {"atr": atr(df).to_numpy()})
    return sg[(sg.fam == "macd12_26_9") & (sg.side == 1) & sg.zero].copy()


def last_signal(df):
    sg = selected_signals(df)
    return sg[sg.t == len(df) - 1]


def fetch(sym, deadline=None):
    """Unadjusted-for-dividends OHLC, exactly as data_layer.fetch(auto_adjust=False)."""
    deadline = time.monotonic() + 12 if deadline is None else deadline
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/" + quote(sym, safe="")
           + "?range=3y&interval=1d&includeAdjustedClose=true")
    for attempt in range(3):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Yahoo deadline exceeded")
        try:
            with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}),
                         timeout=min(3.0, remaining)) as response:
                payload = json.load(response)
            break
        except HTTPError as ex:
            if ex.code == 404:
                # Yahoo's explicit unavailable-history response (e.g. ARX).
                # Transport/rate-limit failures must never masquerade as empty.
                error = json.load(ex).get("chart", {}).get("error", {})
                if error.get("code") == "Not Found":
                    return read_bars(Path("__nonexistent_empty_bars__"))
                raise
            if ex.code != 429 or attempt == 2:
                raise
            time.sleep(min(0.5 * (attempt + 1), max(0, deadline - time.monotonic())))
    chart = payload["chart"]
    if chart.get("error"):
        raise ValueError(f"Yahoo {sym}: {chart['error']}")
    result = chart.get("result")
    if not result:
        raise ValueError(f"Yahoo {sym}: missing result")
    r = result[0]
    if not r.get("timestamp"):
        return read_bars(Path("__nonexistent_empty_bars__"))
    q = r["indicators"]["quote"][0]
    df = pd.DataFrame({k: q[k] for k in ["open", "high", "low", "close", "volume"]})
    df["adj_close"] = r["indicators"].get("adjclose", [{}])[0].get("adjclose", q["close"])
    dates = pd.to_datetime(r["timestamp"], unit="s", utc=True)
    df.index = dates.tz_convert(r["meta"].get("exchangeTimezoneName", "America/Toronto")).normalize().tz_localize(None)
    df.index.name = "date"
    df = df.dropna(subset=["open", "high", "low", "close"])
    # Match data_layer.fetch exactly. S53._clean does its own stricter OHLC
    # check AFTER ATR is computed. FX quotes can have close above reported high.
    df = df[(df.high >= df.low) & (df.close > 0)]
    return df[BAR_COLS].sort_index()


def refresh(syms, live, deadline):
    """Rate-limit request starts to 0.5 s, overlap slow network responses."""
    lock = threading.Lock()
    next_start = [time.monotonic()]

    def job(s):
        with lock:
            delay = max(0, next_start[0] - time.monotonic())
            if delay:
                time.sleep(delay)
            next_start[0] = time.monotonic() + 0.5
        return fetch(s, min(deadline, time.monotonic() + 11))

    frames, errors = {}, []
    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = {pool.submit(job, s): s for s in syms}
        for future in as_completed(jobs):
            s = jobs[future]
            try:
                frames[s] = future.result()
            except Exception as ex:
                errors.append(f"{s}: {ex}")
    if errors:
        raise ValueError("Refresh failed; no orders written: " + "; ".join(errors))
    for s, df in frames.items():
        # Replace overlapping Yahoo rows; retain earlier live history, never p2.
        old = read_bars(live / "bars" / f"{s}.csv")
        if not old.empty and not df.empty:
            df = pd.concat([old[old.index < df.index[0]], df]).sort_index()
        atomic_csv(df, live / "bars" / f"{s}.csv", index=True)
        frames[s] = df
    return frames


def ledger(live):
    p = live / "positions.csv"
    if not p.exists():
        return pd.DataFrame(columns=LEDGER_COLS)
    df = pd.read_csv(p, keep_default_na=False)
    if not set(LEDGER_COLS[:6]).issubset(df):
        raise ValueError("positions.csv is missing required columns")
    # Accept the six-column ledger specified by T36 and upgrade on the next fill.
    for col in LEDGER_COLS[6:]:
        if col not in df:
            df[col] = ""
    for i in df.index:
        if not df.at[i, "trade_id"]:
            df.at[i, "trade_id"] = f"legacy-{i}"
        if df.at[i, "initial_qty"] == "":
            df.at[i, "initial_qty"] = df.at[i, "qty"]
    for col in ["qty", "entry_px", "stop", "initial_qty"]:
        df[col] = pd.to_numeric(df[col], errors="raise")
    df["exit_px"] = pd.to_numeric(df.exit_px.replace("", np.nan), errors="raise")
    df["symbol"] = df.symbol.map(symbol)
    df["status"] = df.status.str.upper()
    if not df.status.isin(["OPEN", "CLOSED"]).all():
        raise ValueError("ledger status must be OPEN or CLOSED")
    if (not np.isfinite(df[["qty", "entry_px", "stop", "initial_qty"]].to_numpy(dtype=float)).all()
            or ((df.qty <= 0) | (df.qty != np.floor(df.qty)) | (df.initial_qty < df.qty)
                | (df.entry_px <= df.stop) | (df.stop <= 0)).any()):
        raise ValueError("invalid ledger quantity or initial risk")
    opened = df[df.status == "OPEN"]
    if opened.symbol.duplicated().any():
        raise ValueError("ledger has multiple open positions for one symbol")
    return df[LEDGER_COLS]


def fill(live, action, sym, qty, price, day, stop=None):
    sym, day = symbol(sym), str(pd.Timestamp(day).date())
    if qty != int(qty) or qty <= 0 or not math.isfinite(price) or price <= 0:
        raise ValueError("fill requires positive whole shares and a positive finite CAD price")
    df = ledger(live)
    opened = df[(df.symbol == sym) & (df.status == "OPEN")]
    if action == "BUY":
        if not opened.empty:
            raise ValueError("one position per stock: BUY already recorded")
        if stop is None or not math.isfinite(stop) or not 0 < stop < price:
            raise ValueError("BUY requires --stop below entry and above zero")
        row = dict(symbol=sym, entry_date=day, qty=qty, entry_px=price, stop=stop,
                   status="OPEN", trade_id=uuid.uuid4().hex, initial_qty=qty, exit_date="", exit_px=np.nan)
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    elif action == "SELL":
        if opened.empty or qty > opened.iloc[0].qty:
            raise ValueError("SELL exceeds the recorded open quantity")
        i, row = opened.index[0], opened.iloc[0].to_dict()
        if day < row["entry_date"]:
            raise ValueError("SELL predates BUY")
        if qty == row["qty"]:
            df.loc[i, ["status", "exit_date", "exit_px"]] = ["CLOSED", day, price]
        else:
            df.at[i, "qty"] -= qty
            row.update(qty=qty, status="CLOSED", exit_date=day, exit_px=price)
            df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    else:
        raise ValueError("action must be BUY or SELL")
    atomic_csv(df, live / "positions.csv")
    print(f"Recorded {action} {qty} {tv_symbol(sym)} @ CAD {price:g} on {day}")


def build_orders(frames, positions, expected, execution, equity_usd, fx):
    rows, candidates, warnings = [], [], []
    held = positions[positions.status == "OPEN"]
    base = dict(equity_usd=equity_usd, usdcad=fx, equity_cad=equity_usd * fx,
                risk_budget_cad=equity_usd * fx * 0.0033)
    for sym, raw in sorted(frames.items()):
        if sym == "CAD=X":
            continue
        df = raw.loc[:expected]
        if df.empty:
            if sym in set(held.symbol):
                fresh(df, expected, sym)
            warnings.append(f"{sym}: empty history; skipped")
            continue
        fresh(df, expected, sym)
        # Reuse the backtest cleaning path for exits as well as signals.
        clean, _, _ = S53._clean(df, {"atr": atr(df).to_numpy()})
        fresh(clean, expected, sym)
        pos = held[held.symbol == sym]
        common = dict(base, symbol=sym, tv_symbol=tv_symbol(sym), signal_date=str(expected.date()),
                      execute_date=str(execution.date()), timing="NEXT_OPEN")
        if not pos.empty:
            p = pos.iloc[0]
            if pd.Timestamp(p.entry_date) > expected:
                raise ValueError(f"{sym}: ledger fill is after scan date")
            since_entry = clean.loc[p.entry_date:]
            hits = since_entry[since_entry.low <= p.stop]
            if not hits.empty:
                rows.append(dict(common, action="CHECK_STOP", qty=p.qty, stop=p.stop,
                                 reason=f"low <= stop since entry; first {hits.index[0].date()}; confirm fill, then record SELL",
                                 timing="VERIFY_PAST_FILL"))
            _, hist = S53._macd(clean.close.astype(float), (12, 26, 9))
            # _sim tests state < 0, including a missed earlier cross. Do not
            # apply EPISODE_GAP or the zero-line entry gate to protective exits.
            if np.isfinite(hist.iloc[-1]) and hist.iloc[-1] < 0:
                rows.append(dict(common, action="SELL", qty=p.qty, stop=p.stop,
                                 reason="histogram < 0 at close (opposite-cross exit); cancel protective stop after fill"))
            if len(since_entry) >= S53.MAX_HOLD:
                warnings.append(f"{sym}: >= {S53.MAX_HOLD} held bars; backtest time-limit reached; review manually")
            continue
        sg = last_signal(df)
        if sg.empty:
            continue
        s = sg.iloc[0]
        entry, stop = float(df.close.iloc[-1]), float(s.anchor - 0.5 * s.A)
        risk = entry - stop
        if stop <= 0 or risk < S53.MIN_R_ATR * s.A:
            warnings.append(f"{sym}: invalid/too-small estimated entry risk; skipped")
            continue
        qty = math.floor(min(base["risk_budget_cad"] / risk, 0.20 * base["equity_cad"] / entry))
        if qty > 0:
            candidates.append(dict(common, action="BUY", qty=qty, entry_est_cad=entry, stop=stop,
                                   atr_pct=float(s.A / entry), reason="S53 IS pick 3; 12/26/9 long zero-line; no weekly gate"))
    slots = max(0, 30 - len(held))  # SELL orders do not free a slot until filled.
    candidates.sort(key=lambda r: (r["atr_pct"], r["symbol"]))
    rows.extend(candidates[:slots])
    if len(candidates) > slots:
        warnings.append(f"{len(candidates)-slots} signals excluded by 30-position capacity")
    return pd.DataFrame(rows, columns=ORDER_COLS), warnings


def account(live):
    p = live / "account.json"
    if not p.exists():
        live.mkdir(parents=True, exist_ok=True)
        # Explicit initial account supplied by T36; existing accounts are never overwritten.
        p.write_text(json.dumps({"equity": 99111.13, "currency": "USD"}, indent=2) + "\n")
    a = json.loads(p.read_text())
    eq = float(a.get("equity", 100000))
    if a.get("currency", "USD") != "USD" or not math.isfinite(eq) or eq <= 0:
        raise ValueError("account requires positive equity in USD")
    return eq


def scan(live, day=None, cached=False):
    expected, execution = session_dates(day)
    df = ledger(live)
    syms = sorted(set(universe()) | set(df[df.status == "OPEN"].symbol) | {"CAD=X"})
    if cached:
        missing = [s for s in syms if not (live / "bars" / f"{s}.csv").exists()]
        if missing:
            raise ValueError("Live cache files missing: " + ", ".join(missing))
    frames = ({s: read_bars(live / "bars" / f"{s}.csv") for s in syms} if cached else
              refresh(syms, live, time.monotonic() + 75))
    fx_bars = frames["CAD=X"].loc[:expected]
    fresh(fx_bars, expected, "CAD=X")
    fx = float(fx_bars.close.iloc[-1])
    if not math.isfinite(fx) or fx <= 0:
        raise ValueError("invalid USDCAD close")
    orders, warnings = build_orders(frames, df, expected, execution, account(live), fx)
    label = expected.strftime("%Y-%m-%d")
    atomic_csv(orders, live / f"orders_{label}.csv")
    md = [f"# S53 paper orders — close {label}", f"Execution: {execution.date()} next TSX open.",
          f"Account USD {orders.equity_usd.iloc[0] if len(orders) else account(live):,.2f}; "
          f"USDCAD {fx:.6f}; equity CAD {account(live)*fx:,.2f}.",
          "All share prices/stops and fills are CAD. Quantities use the last close, not tomorrow's open.",
          "Before entry, recheck risk >= 0.25 ATR, 0.33% risk budget and 20% notional cap at actual open. "
          "Skip invalid gaps; resize down if necessary. Attach the listed protective stop.",
          "CHECK_STOP is a reconciliation alert, not an additional SELL. Confirm remaining shares before a SELL.", "",
          "| Action | Symbol | Qty | Stop CAD | Reason |", "|---|---|---:|---:|---|"]
    for r in orders.itertuples():
        md.append(f"| {r.action} | {r.tv_symbol} | {r.qty:g} | {r.stop:.8f} | {r.reason} |")
    md += ["", *(f"- {w}" for w in warnings)]
    md.append("No orders." if orders.empty else "Record confirmed executions with the fill command; scan never changes positions.")
    (live / f"orders_{label}.md").write_text("\n\n".join(md[:7]) + "\n" + "\n".join(md[7:]) + "\n", encoding="utf-8")
    print(f"{label} -> {execution.date()}: " + str(orders.action.value_counts().to_dict()) + f"; {len(warnings)} warnings")
    for w in warnings:
        print(w)
    return orders


def status(live, day=None):
    df = ledger(live)
    day = pd.Timestamp(day or pd.Timestamp.now(tz="America/Toronto").date())
    realized, daily, unrealized = 0.0, 0.0, 0.0
    marks = []
    for r in df.itertuples():
        denom = r.initial_qty * (r.entry_px - r.stop)
        bars = read_bars(live / "bars" / f"{r.symbol}.csv").loc[:day]
        if r.status == "CLOSED":
            pnl = r.qty * (float(r.exit_px) - r.entry_px)
            realized += pnl / denom
            if pd.Timestamp(r.exit_date) == day:
                prior = bars.loc[bars.index < day]
                ref = r.entry_px if pd.Timestamp(r.entry_date) == day or prior.empty else prior.close.iloc[-1]
                daily += r.qty * (float(r.exit_px) - ref) / denom
        else:
            if bars.empty:
                marks.append(f"{r.symbol}: {r.qty:g} shares; mark unavailable")
                continue
            px = bars.close.iloc[-1]
            prior = bars.loc[bars.index < day]
            ref = r.entry_px if pd.Timestamp(r.entry_date) == day or prior.empty else prior.close.iloc[-1]
            if bars.index[-1] == day:
                daily += r.qty * (px - ref) / denom
            unrealized += r.qty * (px - r.entry_px) / denom
            marks.append(f"{r.symbol}: {r.qty:g} @ {r.entry_px:g}, stop {r.stop:g}, mark {px:g} ({bars.index[-1].date()})")
    closed_ids = set(df[df.status == "CLOSED"].trade_id) - set(df[df.status == "OPEN"].trade_id)
    result = dict(today_R=daily, cumulative_R=realized, unrealized_R=unrealized, trade_count=len(closed_ids))
    print("\n".join(marks) if marks else "No open positions")
    print(json.dumps(result, indent=2))
    print("R uses original CAD fill-to-stop risk, before fees/FX P&L. Review kill rule at 100 completed trades."
          + (" REVIEW DUE." if len(closed_ids) >= 100 else ""))
    return result


def self_test(cache_root):
    from pandas.testing import assert_frame_equal
    # Real modules, real cached prices, no monkeypatches or synthetic substitutes.
    tested = 0
    for sym in ["RY.TO", "TD.TO", "BNS.TO"]:
        bars = read_bars(cache_root / f"{sym}.csv")
        if bars.empty:
            raise AssertionError(f"required parity fixture missing: {sym}")
        expected = S53.signals(bars, {"atr": atr(bars).values})
        expected = expected[(expected.fam == "macd12_26_9") & (expected.side == 1) & expected.zero]
        assert_frame_equal(selected_signals(bars), expected)
        # Dates with buys plus dates without buys; includes the final signal bar.
        times = sorted(set(expected.t.astype(int).tail(8)) | {len(bars)-1, len(bars)-2})
        for t in times:
            prefix = bars.iloc[:t+1]
            assert_frame_equal(last_signal(prefix).reset_index(drop=True),
                               expected[expected.t == t].reset_index(drop=True))
            orders, _ = build_orders({sym: prefix}, ledger(Path(tempfile.gettempdir()) / uuid.uuid4().hex),
                                     prefix.index[-1], prefix.index[-1] + pd.Timedelta(days=1), 100000, 1.4)
            assert len(orders) == len(expected[expected.t == t])
            tested += 1
    print(f"OK real-cache signal + historical-order parity: 3 stocks / {tested} dates")
    d, nxt = session_dates("2026-11-01", pd.Timestamp("2026-11-01T20:00Z"))
    assert d == pd.Timestamp("2026-10-30") and nxt == pd.Timestamp("2026-11-02")
    assert session_dates("2026-10-12", pd.Timestamp("2026-11-01T20:00Z"))[0] == pd.Timestamp("2026-10-09")
    try:
        fresh(bars.iloc[:-1], bars.index[-1], "test")
    except ValueError as ex:
        assert "STALE DATA" in str(ex)
    else:
        raise AssertionError("stale data accepted")
    print("OK stale-data/weekend/TSX holiday guard")
    for s in universe():
        assert symbol(tv_symbol(s)) == s
    assert tv_symbol("BBD-B.TO") == "TSX:BBD.B"
    # Capacity, currency, stop-buffer and low-vol ordering with real signals.
    t = int(expected.t.iloc[-1])
    narrow = bars.iloc[:t+1].copy()
    wide = narrow.copy()
    wide["high"] *= 1.02
    wide["low"] *= .98
    occupied = pd.DataFrame([dict(symbol=f"HELD{i}.TO", status="OPEN") for i in range(29)])
    orders, _ = build_orders({"AAA.TO": narrow, "ZZZ.TO": wide}, occupied,
                             narrow.index[-1], narrow.index[-1] + pd.Timedelta(days=1), 100000, 1.4)
    assert len(orders) == 1 and orders.iloc[0].symbol == "AAA.TO"
    r = orders.iloc[0]
    s = last_signal(narrow).iloc[0]
    assert r.stop == s.anchor - .5 * s.A and r.equity_cad == 140000
    assert r.qty * (r.entry_est_cad-r.stop) <= 462 + 1e-9
    assert r.qty * r.entry_est_cad <= 28000
    occupied = pd.concat([occupied, pd.DataFrame([dict(symbol="HELD29.TO", status="OPEN")])])
    assert build_orders({"AAA.TO": narrow}, occupied, narrow.index[-1], narrow.index[-1], 100000, 1.4)[0].empty
    print("OK CAD sizing/0.5 ATR stop/risk and notional caps/low-vol ranking/30 slots")
    with tempfile.TemporaryDirectory(prefix="t36-") as tmp:
        live = Path(tmp)
        fill(live, "BUY", "RY", 100, 100, "2026-10-29", 90)
        fill(live, "SELL", "RY", 40, 110, "2026-10-30")
        b = pd.DataFrame({"close": [100., 108.]}, index=pd.to_datetime(["2026-10-29", "2026-10-30"]))
        b.index.name = "date"
        atomic_csv(b, live / "bars/RY.TO.csv", index=True)
        r = status(live, "2026-10-30")
        assert np.isclose(r["cumulative_R"], .4) and np.isclose(r["today_R"], .88)
        assert np.isclose(r["unrealized_R"], .48) and r["trade_count"] == 0
        fill(live, "SELL", "RY", 60, 90, "2026-10-30")
        r = status(live, "2026-10-30")
        assert np.isclose(r["cumulative_R"], -.2) and r["trade_count"] == 1
        before = (live / "positions.csv").read_bytes()
        try:
            fill(live, "SELL", "RY", 1, 100, "2026-10-30")
        except ValueError:
            pass
        else:
            raise AssertionError("duplicate sell accepted")
        assert (live / "positions.csv").read_bytes() == before
        (live / "account.json").write_text('{"equity": 99111.13, "currency": "USD"}')
        assert account(live) == 99111.13
        # Full offline scan writes orders, no positions mutation; stale data
        # refuses output even if an earlier valid order file already exists.
        from unittest.mock import patch
        end = narrow.index[-1]
        atomic_csv(narrow, live / "bars/AAA.TO.csv", index=True)
        fx = narrow.copy()
        fx["close"] = 1.4
        atomic_csv(fx, live / "bars/CAD=X.csv", index=True)
        ledger_before = (live / "positions.csv").read_bytes()
        with patch(__name__ + ".universe", return_value=["AAA.TO"]), patch(
                __name__ + ".session_dates", return_value=(end, end + pd.Timedelta(days=1))):
            scan(live, cached=True)
            path = live / f"orders_{end:%Y-%m-%d}.csv"
            saved = path.read_bytes()
            atomic_csv(narrow.iloc[:-1], live / "bars/AAA.TO.csv", index=True)
            try:
                scan(live, cached=True)
            except ValueError as ex:
                assert "STALE DATA" in str(ex)
            else:
                raise AssertionError("scan wrote stale orders")
            assert path.read_bytes() == saved
        assert (live / "positions.csv").read_bytes() == ledger_before
        # Protective exits bypass entry episode suppression; old stop hits
        # remain visible until the actual paper fill is reconciled.
        _, hist = S53._macd(bars.close.astype(float), (12, 26, 9))
        t = int(np.flatnonzero((hist < 0).to_numpy())[-1])
        negative = bars.iloc[:t+1]
        held = pd.DataFrame([dict(symbol="TEST.TO", status="OPEN", qty=10,
                                 entry_date=str(negative.index[-2].date()), stop=float(negative.low.iloc[-1]+.01))])
        exits, _ = build_orders({"TEST.TO": negative}, held, negative.index[-1],
                                negative.index[-1] + pd.Timedelta(days=1), 100000, 1.4)
        assert set(exits.action) == {"SELL", "CHECK_STOP"}
    print("OK symbol mappings/account/partial fills/status arithmetic/idempotent rejection")
    print("OK order-file integration/stale output unchanged/ledger unchanged/protective exits")
    import io
    from unittest.mock import patch
    payload = {"chart": {"result": [{"timestamp": [1793318400], "meta": {"exchangeTimezoneName": "Europe/London"},
                                    "indicators": {"quote": [{"open": [1.3984], "high": [1.3984],
                                    "low": [1.3942], "close": [1.39864], "volume": [0]}]}}], "error": None}}
    rate_limit = HTTPError("test", 429, "limited", {}, io.BytesIO(b"{}"))
    with patch(__name__ + ".urlopen", side_effect=[rate_limit, io.BytesIO(json.dumps(payload).encode())]) as request, patch(
            __name__ + ".time.sleep"):
        fx = fetch("CAD=X")
        assert len(fx) == 1 and fx.close.iloc[0] == 1.39864 and request.call_count == 2
        assert request.call_args.args[0].get_header("User-agent") == "Mozilla/5.0"
    print("OK Yahoo parsing/backtest OHLC cleaning/429 retry/User-Agent")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--live-dir", type=Path, default=LIVE)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("scan")
    s.add_argument("--date")
    s.add_argument("--cached", action="store_true", help="offline live-cache scan; same freshness checks")
    f = sub.add_parser("fill")
    f.add_argument("action", choices=["BUY", "SELL"])
    f.add_argument("symbol")
    f.add_argument("qty", type=int)
    f.add_argument("price", type=float)
    f.add_argument("date")
    f.add_argument("--stop", type=float)
    sub.add_parser("status")
    t = sub.add_parser("self-test")
    t.add_argument("--cache-root", type=Path, default=ROOT / "data/p2/bars")
    args = p.parse_args(argv)
    started = time.perf_counter()
    try:
        if args.command == "scan":
            scan(args.live_dir, args.date, args.cached)
        elif args.command == "fill":
            fill(args.live_dir, args.action, args.symbol, args.qty, args.price, args.date, args.stop)
        elif args.command == "status":
            status(args.live_dir)
        else:
            self_test(args.cache_root)
    except (ValueError, OSError, KeyError) as ex:
        p.exit(1, f"{ex}\n")
    finally:
        print(f"elapsed {time.perf_counter()-started:.3f}s", flush=True)


if __name__ == "__main__":
    main()
