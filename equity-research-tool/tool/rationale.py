"""
The 100-150 word rationale.

Default: built from a fixed template using only numbers already in the scorecard, so every
sentence can be traced back to a row in the report.

Optional (--ai): sends the same scorecard to Claude to write it in more natural prose.
Needs `pip install anthropic` and an ANTHROPIC_API_KEY environment variable. If anything
goes wrong it quietly falls back to the template.
"""
import json
import os

from . import fmt


def _phrase(row):
    return (f"{fmt.METRIC_NAMES[row['metric']]} of {fmt.metric(row['metric'], row['value'])} "
            f"vs a peer median of {fmt.metric(row['metric'], row['peer_median'])}")


def _pick(param, best=True):
    rows = [r for r in param["metrics"] if r["score"] is not None]
    if not rows:
        return None
    return (max if best else min)(rows, key=lambda r: r["score"])


def template_rationale(res):
    c = res["company"]
    params = res["params"]
    ranked = sorted(params.values(), key=lambda p: p["score"], reverse=True)
    strong, weak = ranked[0], ranked[-1]
    t = res["target"]
    d = res["downside"]
    peers = ", ".join(p.replace(".TO", "") for p in res["peers"])

    rank = (f" and ranks #{res['sector_rank']} of {res['sector_size']} in its sector"
            if res.get("sector_rank") else "")
    s = [f"{c['name']} scores {res['weighted_score']:.0f}% against {peers}{rank}, which maps to a {res['call']}"
         + (f" (low confidence: only {fmt.pct(res['data_coverage'], signed=False)} of the score rests on available data)." if res.get("low_confidence") else ".")]
    r = _pick(strong, best=True)
    s.append(f"Its strongest area is {strong['label'].lower()} ({strong['score']:.0f}%)"
             + (f", led by {_phrase(r)}." if r else "."))
    r = _pick(weak, best=False)
    s.append(f"The weakest is {weak['label'].lower()} ({weak['score']:.0f}%)"
             + (f", dragged down by {_phrase(r)}." if r else "."))
    if t.get("target") is not None:
        s.append(f"Applying the peer average forward P/E of {t['peer_avg_pe']:.1f}x to forward EPS of "
                 f"{fmt.money(t['forward_eps'])} gives a target of {fmt.money(t['target'])}, "
                 f"{fmt.pct(t['upside'])} from {fmt.money(c['price'])}.")
    else:
        s.append(f"A P/E-based target couldn't be set ({t.get('error', 'missing data')}).")
    a = res.get("analyst") or {}
    if a.get("target_mean"):
        s.append(f"Analysts' consensus target is {fmt.money(a['target_mean'])} ({fmt.pct(a.get('upside'))}), "
                 f"with {a.get('count') or 'several'} analysts rating it {str(a.get('rating') or 'n/a').title()}.")
    if d.get("max_drawdown") is not None:
        s.append(f"The downside case is a repeat of its five-year max drawdown of {fmt.pct(d['max_drawdown'])}, "
                 f"roughly {fmt.money(d['price_at_max_drawdown'])}.")
    dc = res.get("drawdown_context") or {}
    optional = []
    if dc.get("sector_same_window") is not None:
        optional.append(f"On month-end closes its worst fall was {fmt.pct(dc['stock_drawdown'])}; over the same months "
                        f"the sector index moved {fmt.pct(dc['sector_same_window'])}, so "
                        f"{'most of that fall was company-specific' if dc['excess_vs_sector'] < -0.10 else 'the fall largely tracked the sector'}.")
    if c.get("beta") is not None:
        optional.append(f"Beta of {c['beta']:.2f} means it has moved "
                        + ("less" if c["beta"] < 1 else "more") + " than the market.")
    if any("Review before agreeing" in f for f in res["flags"]):
        s.append("The score and the price target disagree, so this call needs a manual check.")
    for extra in optional:   # add context sentences only while the rationale stays within 150 words
        if len(" ".join(s + [extra]).split()) <= 150:
            s.append(extra)
    return " ".join(s)


def ai_rationale(res, cfg):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None, "ANTHROPIC_API_KEY not set; used template"
    try:
        import anthropic
    except ImportError:
        return None, "anthropic package not installed; used template"

    compact = {
        "company": res["company"]["name"], "ticker": res["company"]["ticker"],
        "call": res["call"], "weighted_score_pct": round(res["weighted_score"], 1),
        "sector_rank": res.get("sector_rank"), "sector_size": res.get("sector_size"),
        "peers": res["peers"],
        "parameters": {
            k: {"weight": p["weight"], "score_pct": round(p["score"], 1),
                "metrics": {r["metric"]: {"value": r["value"], "peer_median": r["peer_median"],
                                          "score": r["score"]} for r in p["metrics"]}}
            for k, p in res["params"].items()},
        "target": {k: v for k, v in res["target"].items() if k in ("target", "upside", "peer_avg_pe", "forward_eps")},
        "price": res["company"]["price"], "downside": res["downside"], "flags": res["flags"],
    }
    max_words = cfg["ai_rationale"]["max_words"]
    prompt = (
        f"Write an equity research rationale of 100-{max_words} words for this stock call. "
        "Use ONLY the numbers in the JSON below; do not add facts, news or numbers that aren't there. "
        "Say why the call is what it is, the strongest and weakest areas, the target price and upside, "
        "and the main risk. Plain prose, no headings or bullets.\n\n"
        + json.dumps(compact, default=str)
    )
    try:
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(model=cfg["ai_rationale"]["model"], max_tokens=400,
                                     messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
        return text, f"written by {cfg['ai_rationale']['model']} from the scorecard"
    except Exception as e:
        return None, f"AI call failed ({e.__class__.__name__}); used template"


def build(res, cfg, use_ai=False):
    note = "template (every number traceable to the scorecard)"
    text = None
    if use_ai:
        text, note = ai_rationale(res, cfg)
    if not text:
        text = template_rationale(res)
    words = text.split()
    limit = cfg["ai_rationale"]["max_words"]
    if len(words) > limit:
        text = " ".join(words[:limit]).rstrip(",;") + "..."
    return text, note, len(text.split())
