"""
Scoring, the Buy/Hold/Sell call, and the target price.

Takes the company snapshot plus its peers' snapshots (plain dictionaries from data.py)
and returns one result dictionary. No internet access here, so it can be tested with
made-up numbers.

HOW A METRIC IS SCORED (0% to 100%)
  score = peers beaten / peers compared            (a tie counts as half a beat)
  Beats every peer -> 100%. Beats none -> 0%. Beats 3 of 5 -> 60%.

HOW A PARAMETER IS SCORED
  The average of its metric scores. A metric with no data is left out of the average and the
  report flags it by name. If none of its metrics has data, it gets a neutral 50%.

DATA COVERAGE
  Per parameter: metrics actually scored / metrics that apply. Overall: weight-averaged.
  Below min_data_coverage in config.json (default 70%), the call is marked low confidence.

THE CALL
  Weighted score = sum of (parameter weight x parameter score).
  >= 70% Buy  |  37.5% to 70% Hold  |  < 37.5% Sell   (thresholds live in config.json;
  they are the brief's 3.8 and 2.5 on a 1-5 scale, converted: (3.8-1)/4 = 70%, (2.5-1)/4 = 37.5%)
"""
import math
from statistics import mean, median

import pandas as pd

from . import calcs, fmt

PARAM_LABELS = {
    "valuation": "Valuation vs peers",
    "profitability": "Profitability",
    "balance_sheet": "Balance sheet & cash flow",
    "growth": "Growth",
    "risk": "Risk",
    "dividend": "Dividend",
}

# Per-metric rule for values that can't be read at face value. Anything not listed is used as-is.
#   "nonpositive_worst": zero or negative ranks worst.
#       P/E, EV/EBITDA, P/B: <= 0 means losses or negative equity, not "cheap".
#       Payout ratio: 0 = no dividend (data.py normally leaves it blank then; see analyze()),
#       negative = paying a dividend out of losses. Both rank worst.
#   "negative_worst": only a negative number ranks worst; zero is a real, valid value.
#       Debt-to-equity: 0 = no debt, which is the BEST case for a lower-is-better metric.
#       Negative D/E means negative shareholders' equity, which ranks worst.
_VALIDITY_RULE = {
    "pe_trailing": "nonpositive_worst",
    "pe_forward": "nonpositive_worst",
    "ev_ebitda": "nonpositive_worst",
    "pb": "nonpositive_worst",
    "payout_ratio": "nonpositive_worst",
    "debt_to_equity": "negative_worst",
}


def _is_missing(value):
    return value is None or (isinstance(value, float) and not math.isfinite(value))


def _clean(metric, value, direction):
    if _is_missing(value):
        return None
    rule = _VALIDITY_RULE.get(metric)
    worst = (math.inf if direction == "lower" else -math.inf)
    if rule == "nonpositive_worst" and value <= 0:
        return worst
    if rule == "negative_worst" and value < 0:
        return worst
    return value


def score_metric(metric, value, peer_values, direction):
    """Returns (score, beats, n_peers) or (None, 0, 0) if it can't be scored."""
    v = _clean(metric, value, direction)
    peers = [p for p in (_clean(metric, x, direction) for x in peer_values) if p is not None]
    if v is None or not peers:
        return None, 0, len(peers)
    beats = 0.0
    for p in peers:
        if v == p:
            beats += 0.5
        elif (v > p) if direction == "higher" else (v < p):
            beats += 1
    return 100 * beats / len(peers), beats, len(peers)


def recommendation(score, thresholds):
    if score >= thresholds["buy_at_or_above"]:
        return "BUY"
    if score >= thresholds["hold_at_or_above"]:
        return "HOLD"
    return "SELL"


def target_price(company, peers, cfg):
    """Target = average peer forward P/E x company's forward EPS."""
    tp = cfg["target_price"]
    used, dropped = {}, {}
    for p in peers:
        pe = p.get("pe_forward")
        basis = "forward"
        if pe is None:
            pe, basis = p.get("pe_trailing"), "trailing (no forward P/E)"
        if pe is None:
            continue
        if tp["min_peer_pe"] <= pe <= tp["max_peer_pe"]:
            used[p["ticker"]] = {"pe": pe, "basis": basis}
        else:
            dropped[p["ticker"]] = pe

    out = {"peer_pes_used": used, "peer_pes_dropped": dropped, "price": company["price"]}
    eps = company.get("eps_forward")
    out["forward_eps"] = eps
    if not used:
        out["error"] = "No usable peer P/E"
        return out
    avg_pe = mean(v["pe"] for v in used.values())
    out["peer_avg_pe"] = avg_pe
    if eps is None or eps <= 0:
        out["error"] = "Forward EPS missing or negative; P/E target not meaningful"
        return out
    out["target"] = avg_pe * eps
    out["upside"] = out["target"] / company["price"] - 1

    # Cross-check on book value (the primary lens for banks): peer average P/B x book value per share.
    pbs = [p["pb"] for p in peers if p.get("pb") and p["pb"] > 0]
    bvps = company.get("book_value_per_share")
    if pbs and bvps:
        out["pb_cross_check"] = {"peer_avg_pb": mean(pbs), "bvps": bvps, "target": mean(pbs) * bvps}
    return out


def _series(snap):
    mp = snap.get("monthly_prices")
    if not mp:
        return None
    s = pd.Series(mp, dtype=float)
    s.index = pd.PeriodIndex(s.index, freq="M")
    return s.sort_index()


def drawdown_vs_sector(company, peers):
    """Puts the stock's worst fall in context.

    1. Find the stock's worst peak-to-trough fall on month-end closes, and the two months it ran between.
    2. Over those same months, how did each peer move, and an equal-weighted sector index?
    3. Separately, the sector index's own worst fall over the period.
    Sector index = average of the peers' prices (this stock excluded) rebased to 1.0 at the first common month.
    """
    s = _series(company)
    if s is None:
        return {"error": "No price history for the company"}
    mdd, peak, trough = calcs.drawdown_window(s)
    out = {"stock_drawdown": mdd, "peak": str(peak), "trough": str(trough), "peers": {},
           "basis": "month-end closes"}
    members = {}
    for p in peers:
        ps = _series(p)
        if ps is None:
            out["peers"][p["ticker"]] = None
            continue
        members[p["ticker"]] = ps
        out["peers"][p["ticker"]] = (float(ps[trough] / ps[peak] - 1)
                                     if peak in ps.index and trough in ps.index else None)
    moves = [v for v in out["peers"].values() if v is not None]
    out["peer_avg_same_window"] = mean(moves) if moves else None
    if len(members) >= 2:
        df = pd.concat(members, axis=1, join="inner").dropna()
        if len(df) < 2:
            # Peers' histories don't share at least two months (e.g. stale saved data, or a peer
            # that listed/delisted in a different period). Skip the sector index rather than crash.
            out["sector_error"] = "peers lack overlapping price history"
        else:
            index = (df / df.iloc[0]).mean(axis=1)
            out["sector_members"] = list(df.columns)
            if peak in index.index and trough in index.index:
                out["sector_same_window"] = float(index[trough] / index[peak] - 1)
            smdd, speak, strough = calcs.drawdown_window(index)
            out["sector_max_drawdown"] = smdd
            out["sector_peak"], out["sector_trough"] = str(speak), str(strough)
    if out.get("sector_same_window") is not None:
        out["excess_vs_sector"] = mdd - out["sector_same_window"]
    return out


def analyst_view(company):
    a = company.get("analyst") or {}
    tgt = a.get("target_mean")
    return {**a, "upside": (tgt / company["price"] - 1) if tgt else None}


def analyze(company, peers, cfg):
    sector = company.get("sector", "default")
    weights = cfg["weights"].get(sector, cfg["weights"]["default"])
    metric_map = cfg["metrics"].get(sector, cfg["metrics"]["default"])
    flags = []
    min_cov = cfg.get("min_data_coverage", 0.70)

    params = {}
    for param, metric_list in metric_map.items():
        rows = []
        applicable = 0
        for metric, direction in metric_list:
            peer_vals = {p["ticker"]: p.get(metric) for p in peers}
            s, beats, n = score_metric(metric, company.get(metric), list(peer_vals.values()), direction)
            valid_peer = [x for x in peer_vals.values() if not _is_missing(x)]
            # Payout ratio is blank for a company that pays no dividend. That's "not applicable"
            # (the dividend yield of 0 already scores it), so it doesn't count against coverage.
            not_applicable = (metric == "payout_ratio" and _is_missing(company.get(metric))
                              and company.get("dps_ttm") == 0)
            if not not_applicable:
                applicable += 1
                if s is None:
                    name = fmt.METRIC_NAMES.get(metric, metric)
                    why = ("company figure unavailable" if _is_missing(company.get(metric))
                           else "no peer figures to compare")
                    flags.append(f"{PARAM_LABELS[param]}: {name} excluded from score ({why})")
            rows.append({
                "metric": metric,
                "direction": direction,
                "value": company.get(metric),
                "peers": peer_vals,
                "peer_median": median(valid_peer) if valid_peer else None,
                "beats": beats,
                "n_peers": n,
                "score": s,
                "not_applicable": not_applicable,
            })
        scored = [r["score"] for r in rows if r["score"] is not None]
        if scored:
            pscore = mean(scored)
        else:
            pscore = 50.0
            flags.append(f"{PARAM_LABELS[param]}: no usable data, scored neutral 50%")
        params[param] = {
            "label": PARAM_LABELS[param],
            "weight": weights[param],
            "score": pscore,
            "contribution": weights[param] * pscore,
            "coverage": (len(scored) / applicable) if applicable else 1.0,
            "metrics": rows,
        }

    total_w = sum(p["weight"] for p in params.values())
    if abs(total_w - 1) > 1e-6:
        flags.append(f"Weights add to {total_w:.2f}, not 1.00; check config.json")
    weighted = sum(p["contribution"] for p in params.values()) / total_w
    call = recommendation(weighted, cfg["thresholds"])
    # Share of the score (by parameter weight) that rests on real data rather than on gaps.
    coverage = sum(p["weight"] * p["coverage"] for p in params.values()) / total_w
    low_confidence = coverage < min_cov
    if low_confidence:
        flags.insert(0, f"Low data coverage ({coverage * 100:.0f}%, below {min_cov * 100:.0f}%): "
                        "treat the recommendation as low confidence")

    tgt = target_price(company, peers, cfg)
    mdd = company.get("max_drawdown")
    downside = {"max_drawdown": mdd, "price_at_max_drawdown": company["price"] * (1 + mdd) if mdd is not None else None}

    up = tgt.get("upside")
    if up is not None:
        if call == "BUY" and up < 0:
            flags.append("Score says BUY but the P/E target is below today's price. Review before agreeing.")
        if call == "SELL" and up > 0.10:
            flags.append("Score says SELL but the P/E target shows >10% upside. Review before agreeing.")

    analyst = analyst_view(company)
    if analyst.get("target_mean") and tgt.get("target"):
        gap = tgt["target"] / analyst["target_mean"] - 1
        analyst["tool_vs_analyst"] = gap
        if abs(gap) > 0.15:
            flags.append(f"Tool target is {gap * 100:+.0f}% vs the analyst consensus target. Worth explaining.")
    if analyst.get("upside") is not None and up is not None and (analyst["upside"] > 0) != (up > 0):
        flags.append("Analysts and the tool disagree on direction (one shows upside, the other downside).")
    dd_ctx = drawdown_vs_sector(company, peers)
    if dd_ctx.get("sector_error"):
        flags.append(f"Sector drawdown comparison unavailable: {dd_ctx['sector_error']}")
    if dd_ctx.get("excess_vs_sector") is not None and dd_ctx["excess_vs_sector"] < -0.10:
        flags.append("Its worst fall was more than 10 points deeper than the sector's over the same months: stock-specific risk.")

    return {
        "company": company,
        "peers": [p["ticker"] for p in peers],
        "peer_names": {p["ticker"]: p.get("name") for p in peers},
        "sector_model": sector,
        "weights": weights,
        "params": params,
        "weighted_score": weighted,
        "call": call,
        "data_coverage": coverage,
        "low_confidence": low_confidence,
        "thresholds": cfg["thresholds"],
        "target": tgt,
        "downside": downside,
        "analyst": analyst,
        "drawdown_context": dd_ctx,
        "flags": flags + company.get("notes", []),
    }


def rank_sector(snapshots, cfg):
    """Score every company against all the others in the group and rank them, best first."""
    results = []
    for s in snapshots:
        others = [o for o in snapshots if o["ticker"] != s["ticker"]]
        results.append(analyze(s, others, cfg))
    results.sort(key=lambda r: r["weighted_score"], reverse=True)
    for i, r in enumerate(results, 1):
        r["sector_rank"] = i
        r["sector_size"] = len(results)
    return results
