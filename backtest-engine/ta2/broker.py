"""Broker layer: Interactive Brokers (paper by default) behind a small interface, plus an offline stub.

Everything the bot needs from a broker is the Broker interface below, so the whole daily routine can be
tested offline with StubBroker and then run unchanged against IBKR.

  IB Gateway / TWS must be running and signed in, with API enabled
  (Gateway: Configure > Settings > API > Settings; TWS: File > Global Configuration > API > Settings;
   tick "Enable ActiveX and Socket Clients", leave "Read-Only API" OFF to place orders).
  Default ports: Gateway paper 4002, Gateway live 4001, TWS paper 7497, TWS live 7496.

SAFETY (two independent guards, both must pass):
  1. the port must be a paper port, and
  2. the IBKR account id must start with DU/DF (IBKR's paper prefix),
  unless allow_live=True is passed explicitly. The bot never passes it.

Orders: entry = MARKET (DAY) with a STOP child attached (parent/child, so the stop only goes live when the
entry fills, and is cancelled if the entry is cancelled). Exit = cancel the protective stop, then MARKET sell.
"""
from __future__ import annotations
import json, math, time
from dataclasses import dataclass, field
from pathlib import Path
import pandas as pd

PAPER_PORTS = {4002, 7497}
LIVE_PORTS = {4001, 7496}


@dataclass
class Position:
    symbol: str          # our symbol, e.g. "RY.TO"
    qty: float
    avg_cost: float


@dataclass
class Fill:
    symbol: str
    side: str            # BUY / SELL
    qty: float
    price: float
    time: pd.Timestamp
    order_ref: str = ""


class Broker:
    """Interface used by ta2.bot."""
    name = "broker"
    currency = "CAD"

    def connect(self): raise NotImplementedError
    def disconnect(self): pass
    def account_id(self) -> str: raise NotImplementedError
    def equity(self) -> tuple[float, str]: raise NotImplementedError
    def positions(self) -> list[Position]: raise NotImplementedError
    def open_orders(self) -> pd.DataFrame: raise NotImplementedError
    def price(self, symbol: str) -> float: raise NotImplementedError
    def place_entry(self, symbol, qty, stop_price, ref="") -> dict: raise NotImplementedError
    def place_exit(self, symbol, qty, ref="") -> dict: raise NotImplementedError
    def cancel_protective(self, symbol) -> int: raise NotImplementedError
    def fills(self, since: pd.Timestamp | None = None) -> list[Fill]: raise NotImplementedError
    def is_open(self) -> bool: return True


# ------------------------------------------------------------------ Interactive Brokers
def _variants(sym: str):
    """TSX class shares: our 'CCL-B' is 'CCL.B' / 'CCL B' / 'CCL-B' at IBKR, depending on the name."""
    base = sym.replace(".TO", "")
    if "-" in base:
        a, b = base.split("-", 1)
        return [f"{a}.{b}", f"{a} {b}", f"{a}-{b}", base]
    return [base]


class IBKRBroker(Broker):
    name = "IBKR"

    def __init__(self, host="127.0.0.1", port=4002, client_id=17, account="", allow_live=False,
                 currency="CAD", exchange="SMART", primary="TSE", cache=None, timeout=10.0):
        if port in LIVE_PORTS and not allow_live:
            raise PermissionError(
                f"port {port} is an IB LIVE port. ta2.bot only trades the paper account. "
                f"Start IB Gateway/TWS logged in with your PAPER username and use port "
                f"{'4002 (Gateway)' if port == 4001 else '7497 (TWS)'}.")
        if port not in PAPER_PORTS and not allow_live:
            raise PermissionError(f"port {port} is not a known IB paper port {sorted(PAPER_PORTS)}; pass allow_live=True to override")
        self.host, self.port, self.client_id = host, int(port), int(client_id)
        self.account, self.allow_live, self.timeout = account, allow_live, timeout
        self.currency, self.exchange, self.primary = currency, exchange, primary
        self.cache_path = Path(cache) if cache else None
        self._conid = json.loads(self.cache_path.read_text()) if self.cache_path and self.cache_path.exists() else {}
        self.ib = None

    # -- connection
    def connect(self):
        try:
            from ib_async import IB
        except ImportError:
            try:
                from ib_insync import IB            # older name, same API
            except ImportError as ex:
                raise ImportError("pip install ib_async (or ib_insync) to trade through IBKR") from ex
        self.ib = IB()
        try:
            self.ib.connect(self.host, self.port, clientId=self.client_id, timeout=self.timeout,
                            account=self.account)
        except Exception as ex:
            raise ConnectionError(
                f"cannot reach IB API at {self.host}:{self.port} ({ex}). Checklist: IB Gateway/TWS running and "
                f"logged in (paper username); API enabled; 'Read-Only API' off; this machine allowed under "
                f"Trusted IPs if not localhost.") from ex
        accounts = list(self.ib.managedAccounts())
        if not self.account:
            paper = [a for a in accounts if a.upper().startswith(("DU", "DF"))]
            self.account = (paper or accounts)[0] if accounts else ""
        if self.account not in accounts and accounts:
            raise ValueError(f"account {self.account} not in this login's accounts {accounts}")
        if not self.account.upper().startswith(("DU", "DF")) and not self.allow_live:
            self.disconnect()
            raise PermissionError(
                f"account {self.account} is not an IBKR paper account (paper ids start with DU/DF). "
                "Log IB Gateway/TWS in with the paper username, or pass allow_live=True deliberately.")
        return self

    def disconnect(self):
        if self.ib is not None and self.ib.isConnected():
            self.ib.disconnect()

    def account_id(self):
        return self.account

    def is_paper(self):
        return self.account.upper().startswith(("DU", "DF")) and self.port in PAPER_PORTS

    # -- contracts
    def contract(self, symbol):
        from ib_async import Stock
        if symbol in self._conid:
            c = Stock(conId=self._conid[symbol][0], symbol=self._conid[symbol][1],
                      exchange=self.exchange, currency=self.currency)
            self.ib.qualifyContracts(c)
            return c
        last = None
        for v in _variants(symbol):
            c = Stock(v, self.exchange, self.currency, primaryExchange=self.primary)
            try:
                d = self.ib.reqContractDetails(c)
            except Exception as ex:
                last = ex; d = []
            if d:
                got = d[0].contract
                self._conid[symbol] = [got.conId, got.symbol]
                if self.cache_path:
                    self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                    self.cache_path.write_text(json.dumps(self._conid, indent=1))
                return got
        raise ValueError(f"IBKR has no {self.currency} contract for {symbol} (tried {_variants(symbol)}): {last}")

    def our_symbol(self, ib_symbol):
        for ours, (cid, sym) in self._conid.items():
            if sym == ib_symbol:
                return ours
        return ib_symbol.replace(".", "-").replace(" ", "-") + ".TO"

    # -- state
    def equity(self):
        rows = self.ib.accountSummary(self.account)
        vals = {r.tag: r for r in rows if r.account in (self.account, "All")}
        nl = vals.get("NetLiquidation")
        if nl is None:
            raise ValueError("IB did not return NetLiquidation; is the account funded/subscribed?")
        return float(nl.value), nl.currency

    def positions(self):
        out = []
        for p in self.ib.positions(self.account):
            if p.contract.secType != "STK" or (p.position or 0) == 0:
                continue
            out.append(Position(self.our_symbol(p.contract.symbol), float(p.position), float(p.avgCost)))
        return out

    def open_orders(self):
        rows = []
        for t in self.ib.openTrades():
            if t.order.account and t.order.account != self.account:
                continue
            rows.append(dict(symbol=self.our_symbol(t.contract.symbol), order_id=t.order.orderId,
                             action=t.order.action, qty=float(t.order.totalQuantity),
                             type=t.order.orderType, stop=float(t.order.auxPrice or 0),
                             ref=t.order.orderRef or "", status=t.orderStatus.status))
        return pd.DataFrame(rows, columns=["symbol", "order_id", "action", "qty", "type", "stop", "ref", "status"])

    def price(self, symbol):
        """Last traded price (delayed data is fine; the bot only uses it for sizing)."""
        c = self.contract(symbol)
        self.ib.reqMarketDataType(3)            # 1 live, 3 delayed - delayed needs no subscription
        tk = self.ib.reqMktData(c, snapshot=False)
        for _ in range(40):
            self.ib.sleep(0.25)
            for v in (tk.last, tk.close, tk.marketPrice()):
                if v is not None and not (isinstance(v, float) and math.isnan(v)) and v > 0:
                    self.ib.cancelMktData(c)
                    return float(v)
        self.ib.cancelMktData(c)
        raise ValueError(f"no price for {symbol} (market closed and no close tick?)")

    # -- orders
    def place_entry(self, symbol, qty, stop_price, ref=""):
        from ib_async import MarketOrder, StopOrder
        c = self.contract(symbol)
        parent = MarketOrder("BUY", qty, account=self.account, orderRef=ref, tif="DAY", transmit=False)
        pt = self.ib.placeOrder(c, parent)
        stop = StopOrder("SELL", qty, round(float(stop_price), 2), account=self.account,
                         orderRef=(ref + "|stop") if ref else "stop", tif="GTC",
                         parentId=pt.order.orderId, transmit=True)
        st = self.ib.placeOrder(c, stop)
        self.ib.sleep(1.0)
        return dict(symbol=symbol, qty=qty, entry_order=pt.order.orderId, stop_order=st.order.orderId,
                    stop=round(float(stop_price), 2), status=pt.orderStatus.status)

    def cancel_protective(self, symbol):
        n = 0
        for t in self.ib.openTrades():
            if (self.our_symbol(t.contract.symbol) == symbol and t.order.action == "SELL"
                    and t.order.orderType in ("STP", "STP LMT")):
                self.ib.cancelOrder(t.order); n += 1
        if n:
            self.ib.sleep(1.0)
        return n

    def place_exit(self, symbol, qty, ref=""):
        from ib_async import MarketOrder
        self.cancel_protective(symbol)          # never leave a stop that could sell the same shares twice
        c = self.contract(symbol)
        t = self.ib.placeOrder(c, MarketOrder("SELL", qty, account=self.account, orderRef=ref, tif="DAY"))
        self.ib.sleep(1.0)
        return dict(symbol=symbol, qty=qty, exit_order=t.order.orderId, status=t.orderStatus.status)

    def fills(self, since=None):
        out = []
        for f in self.ib.fills():
            if f.execution.acctNumber and f.execution.acctNumber != self.account:
                continue
            ts = pd.Timestamp(f.execution.time).tz_convert("America/Toronto").tz_localize(None)
            if since is not None and ts < pd.Timestamp(since):
                continue
            out.append(Fill(self.our_symbol(f.contract.symbol), f.execution.side.replace("BOT", "BUY").replace("SLD", "SELL"),
                            float(f.execution.shares), float(f.execution.price), ts, f.execution.orderRef or ""))
        return out

    def is_open(self):
        """True if the TSX is in its regular session right now (IB contract hours)."""
        try:
            d = self.ib.reqContractDetails(self.contract("RY.TO"))[0]
            now = pd.Timestamp.now(tz="America/Toronto").tz_localize(None)
            for span in (d.liquidHours or "").split(";"):
                if "CLOSED" in span or "-" not in span:
                    continue
                a, b = span.split("-")
                fmt = "%Y%m%d:%H%M"
                if pd.Timestamp(pd.to_datetime(a, format=fmt)) <= now <= pd.Timestamp(pd.to_datetime(b, format=fmt)):
                    return True
            return False
        except Exception:
            return False


# ------------------------------------------------------------------ offline stub (tests / dry runs)
@dataclass
class StubBroker(Broker):
    """In-memory broker: fills market orders instantly at `prices`, keeps stops as resting orders.
    Used by the tests and by `bot --broker stub` so the whole routine can be exercised with no network."""
    name: str = "stub"
    start_equity: float = 100_000.0
    prices: dict = field(default_factory=dict)
    account: str = "DU0000000"
    currency: str = "CAD"
    _pos: dict = field(default_factory=dict)
    _orders: list = field(default_factory=list)
    _fills: list = field(default_factory=list)
    _cash: float = 0.0
    _oid: int = 0

    def connect(self): self._cash = self._cash or self.start_equity; return self
    def account_id(self): return self.account
    def is_paper(self): return True
    def equity(self):
        mv = sum(q * self.prices.get(s, 0) for s, (q, _) in self._pos.items())
        return self._cash + mv, self.currency
    def positions(self): return [Position(s, q, c) for s, (q, c) in self._pos.items() if q]
    def open_orders(self): return pd.DataFrame(self._orders, columns=["symbol", "order_id", "action", "qty", "type", "stop", "ref", "status"])
    def price(self, symbol):
        if symbol not in self.prices:
            raise ValueError(f"stub has no price for {symbol}")
        return self.prices[symbol]

    def place_entry(self, symbol, qty, stop_price, ref=""):
        px = self.price(symbol); self._oid += 1; eid = self._oid
        self._cash -= qty * px
        q0, c0 = self._pos.get(symbol, (0, 0.0))
        self._pos[symbol] = (q0 + qty, (q0 * c0 + qty * px) / (q0 + qty))
        self._fills.append(Fill(symbol, "BUY", qty, px, pd.Timestamp.now().normalize(), ref))
        self._oid += 1
        self._orders.append(dict(symbol=symbol, order_id=self._oid, action="SELL", qty=qty, type="STP",
                                 stop=round(float(stop_price), 2), ref=(ref + "|stop"), status="PreSubmitted"))
        return dict(symbol=symbol, qty=qty, entry_order=eid, stop_order=self._oid,
                    stop=round(float(stop_price), 2), status="Filled")

    def cancel_protective(self, symbol):
        n = len([o for o in self._orders if o["symbol"] == symbol and o["type"] == "STP"])
        self._orders = [o for o in self._orders if not (o["symbol"] == symbol and o["type"] == "STP")]
        return n

    def place_exit(self, symbol, qty, ref=""):
        self.cancel_protective(symbol)
        px = self.price(symbol); self._cash += qty * px; self._oid += 1
        q0, c0 = self._pos.get(symbol, (0, 0.0))
        self._pos[symbol] = (q0 - qty, c0)
        if abs(self._pos[symbol][0]) < 1e-9:
            self._pos.pop(symbol)
        self._fills.append(Fill(symbol, "SELL", qty, px, pd.Timestamp.now().normalize(), ref))
        return dict(symbol=symbol, qty=qty, exit_order=self._oid, status="Filled")

    def fills(self, since=None):
        return [f for f in self._fills if since is None or f.time >= pd.Timestamp(since)]


def get(kind="ibkr", **kw) -> Broker:
    return StubBroker(**kw) if kind == "stub" else IBKRBroker(**kw)
