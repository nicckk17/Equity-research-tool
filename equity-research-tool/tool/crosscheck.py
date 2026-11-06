"""
Second-source check against TMX (the company that runs the TSX), via the free openbb-tmx package:
    pip install openbb-core openbb-tmx

It does NOT change any score. It compares Yahoo's headline numbers with TMX's for each company and
adds a flag to the report when they disagree by more than the tolerance below, so you can see
which figure to verify against the company's own filings.
"""
import asyncio
import math

# metric -> (kind, tolerance). "rel" = % difference, "abs" = percentage-point difference (decimals).
TOLERANCE = {
    "price":          ("rel", 0.02),
    "market_cap":     ("rel", 0.05),
    "pe_trailing":    ("rel", 0.10),
    "pb":             ("rel", 0.10),
    "dividend_yield": ("abs", 0.005),
    "roe":            ("abs", 0.03),
}
LABELS = {"price": "Price", "market_cap": "Market cap", "pe_trailing": "P/E (trailing)", "pb": "P/B",
          "dividend_yield": "Dividend yield", "roe": "ROE"}


def _f(x):
    """Float, or None for missing / non-numeric / NaN / infinite (so they can't pass as agreement)."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def tmx_view(q):
    """Map one TMX quote record (dict) onto our metric names."""
    return {
        "price": _f(q.get("last_price")),
        "market_cap": _f(q.get("market_cap")),
        "pe_trailing": _f(q.get("pe")),
        "pb": _f(q.get("price_to_book")),
        "dividend_yield": _f(q.get("div_yield")),
        "roe": _f(q.get("return_on_equity")),
    }


def compare(snap, tmx):
    """Return a list of human-readable disagreements between a Yahoo snapshot and a TMX view."""
    return compare_detail(snap, tmx)["disagreements"]


def compare_detail(snap, tmx):
    """Which metrics were actually compared, which weren't, and the disagreements among those compared."""
    out, compared, skipped = [], [], []
    for key, (kind, tol) in TOLERANCE.items():
        y, t = _f(snap.get(key)), _f(tmx.get(key))
        if y is None or t is None or (kind == "rel" and t == 0):
            skipped.append(key)
            continue
        compared.append(key)
        if kind == "rel":
            gap = abs(y - t) / abs(t) if t else None
            bad = gap is not None and gap > tol
            desc = f"{gap * 100:.0f}% apart" if gap is not None else ""
        else:
            gap = abs(y - t)
            bad = gap > tol
            desc = f"{gap * 100:.1f} points apart"
        if bad:
            fmt = (lambda v: f"{v * 100:.2f}%") if kind == "abs" else (lambda v: f"{v:,.2f}")
            out.append(f"{LABELS[key]}: Yahoo {fmt(y)} vs TMX {fmt(t)} ({desc}). Check the company's filings.")
    return {"disagreements": out, "compared": compared, "not_compared": skipped}


def fetch_quotes(tickers):
    """Batch-fetch TMX quotes. Returns {ticker: view}. Raises if openbb-tmx isn't installed or TMX is unreachable."""
    from openbb_tmx.models.equity_quote import TmxEquityQuoteFetcher
    base = {t: t.replace(".TO", "") for t in tickers}
    data = asyncio.run(TmxEquityQuoteFetcher.fetch_data({"symbol": ",".join(base.values())}, {}))
    by_sym = {d.symbol: d.model_dump() for d in data}
    return {t: tmx_view(by_sym[b]) for t, b in base.items() if b in by_sym}


def apply(snaps):
    """Add TMX numbers and disagreement flags to each snapshot in place. Fails soft."""
    try:
        quotes = fetch_quotes([s["ticker"] for s in snaps])
    except Exception as e:
        print(f"  ! TMX cross-check skipped: {type(e).__name__}: {e}")
        return
    for s in snaps:
        view = quotes.get(s["ticker"])
        if not view:
            s["notes"].append("TMX cross-check: no TMX quote found for this ticker")
            continue
        s["tmx"] = view
        s["notes"].extend(apply_one(s, view))


def apply_one(snap, view):
    """Notes for one company. Only metrics present on both sides count as checked."""
    det = compare_detail(snap, view)
    n, total = len(det["compared"]), len(TOLERANCE)
    snap["tmx_compared"] = det["compared"]
    if n == 0:
        return ["TMX cross-check: no usable TMX data for these metrics; nothing was verified"]
    notes = [f"TMX cross-check: {d}" for d in det["disagreements"]]
    missing = ", ".join(LABELS[k] for k in det["not_compared"])
    if not det["disagreements"]:
        names = ", ".join(LABELS[k] for k in det["compared"])
        notes.append(f"TMX cross-check: {n}/{total} compared ({names}), all within tolerance"
                     + (f"; not available: {missing}" if missing else ""))
    elif missing:
        notes.append(f"TMX cross-check: {n}/{total} compared; not available: {missing}")
    return notes
