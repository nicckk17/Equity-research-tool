"""Writes the results: a one-screen console summary, an HTML report you open in a browser, and a JSON file."""
import html
import json
import os
from datetime import date

from . import fmt

CALL_COLOURS = {"BUY": "#1a7f37", "HOLD": "#9a6700", "SELL": "#cf222e"}


def console_summary(res, rationale):
    c, t, d = res["company"], res["target"], res["downside"]
    lines = [
        "",
        f"  {c['name']} ({c['ticker']})   price {fmt.money(c['price'])} {c.get('currency') or ''}",
        f"  Peers: {', '.join(res['peers'])}   model: {res['sector_model']}",
        "",
        f"  RECOMMENDATION   {res['call']}{' (LOW CONFIDENCE)' if res.get('low_confidence') else ''}   "
        f"(weighted score {res['weighted_score']:.1f}%, data coverage {fmt.pct(res.get('data_coverage'), signed=False)})"
        + (f"   sector rank #{res['sector_rank']} of {res['sector_size']}" if res.get("sector_rank") else ""),
        f"  Analyst target   {fmt.money((res.get('analyst') or {}).get('target_mean'))}  ({fmt.pct((res.get('analyst') or {}).get('upside'))})",
        f"  Tool target      {fmt.money(t.get('target'))}  ({fmt.pct(t.get('upside'))})",
        f"  Downside         {fmt.pct(d.get('max_drawdown'))}  (5-yr max drawdown, daily closes -> {fmt.money(d.get('price_at_max_drawdown'))})",
        "",
        "  Parameter                     Weight  Score   Weight x score",
    ]
    for p in res["params"].values():
        lines.append(f"  {p['label']:<29} {p['weight'] * 100:>5.0f}%  {p['score']:>5.1f}%  {p['contribution']:>6.1f} pts")
    lines += ["", "  Rationale:", "  " + rationale, ""]
    if res["flags"]:
        lines.append("  Flags:")
        lines += [f"   - {f}" for f in res["flags"]]
        lines.append("")
    return "\n".join(lines)


def _e(x):
    return html.escape(str(x))


def html_report(res, rationale, rationale_note, word_count):
    c, t, d = res["company"], res["target"], res["downside"]
    colour = CALL_COLOURS[res["call"]]
    peers = res["peers"]

    score_rows = "".join(
        f"<tr><td>{_e(p['label'])}</td><td class=n>{p['weight'] * 100:.0f}%</td>"
        f"<td class=n>{p['score']:.1f}%</td><td class=n>{p['contribution']:.1f}</td></tr>"
        for p in res["params"].values())

    detail = []
    for p in res["params"].values():
        detail.append(f"<tr class=grp><td colspan={5 + len(peers)}>{_e(p['label'])} "
                      f"&mdash; score {p['score']:.1f}%</td></tr>")
        for r in p["metrics"]:
            m = r["metric"]
            better = "higher" if r["direction"] == "higher" else "lower"
            peer_cells = "".join(f"<td class=n>{fmt.metric(m, r['peers'].get(pk))}</td>" for pk in peers)
            score = f"{r['score']:.0f}%" if r["score"] is not None else "n/a"
            beats = f"{r['beats']:g} of {r['n_peers']}" if r["score"] is not None else "&ndash;"
            detail.append(
                f"<tr><td>{_e(fmt.METRIC_NAMES[m])} <span class=dim>({better} better)</span></td>"
                f"<td class='n b'>{fmt.metric(m, r['value'])}</td>{peer_cells}"
                f"<td class=n>{fmt.metric(m, r['peer_median'])}</td><td class=n>{beats}</td>"
                f"<td class='n b'>{score}</td></tr>")
    peer_heads = "".join(f"<th class=n>{_e(pk.replace('.TO', ''))}</th>" for pk in peers)

    tp_lines = []
    for tk, v in t.get("peer_pes_used", {}).items():
        tp_lines.append(f"<li>{_e(tk)}: {v['pe']:.1f}x ({_e(v['basis'])})</li>")
    for tk, v in t.get("peer_pes_dropped", {}).items():
        tp_lines.append(f"<li class=dim>{_e(tk)}: {v:.1f}x, dropped as outlier</li>")
    if t.get("target") is not None:
        tp_calc = (f"<p>Peer average forward P/E <b>{t['peer_avg_pe']:.2f}x</b> &times; forward EPS "
                   f"<b>{fmt.money(t['forward_eps'])}</b> = target <b>{fmt.money(t['target'])}</b></p>"
                   f"<p>Upside = {fmt.money(t['target'])} &divide; {fmt.money(c['price'])} &minus; 1 = "
                   f"<b>{fmt.pct(t['upside'])}</b></p>")
    else:
        tp_calc = f"<p><b>No P/E target:</b> {_e(t.get('error'))}</p>"
    pbx = t.get("pb_cross_check")
    if pbx:
        tp_calc += (f"<p class=dim>Cross-check on book value: peer average P/B {pbx['peer_avg_pb']:.2f}x &times; "
                    f"book value/share {fmt.money(pbx['bvps'])} = {fmt.money(pbx['target'])}"
                    f" ({fmt.pct(pbx['target'] / c['price'] - 1)})</p>")

    flags = "".join(f"<li>{_e(f)}</li>" for f in res["flags"]) or "<li>None</li>"
    weights = ", ".join(f"{fmt_label}: {w * 100:.0f}%" for fmt_label, w in
                        ((res["params"][k]["label"], v) for k, v in res["weights"].items()))
    th = res["thresholds"]

    a = res.get("analyst") or {}
    rank_box = (f" <div><span>Sector rank</span><b>#{res['sector_rank']} <small class=dim>of {res['sector_size']}</small></b></div>\n"
                if res.get("sector_rank") else "")
    if a.get("target_mean"):
        rng = (f"{fmt.money(a.get('target_low'))} &ndash; {fmt.money(a.get('target_high'))}"
               if a.get("target_low") else "")
        who = f"{a.get('count') or '?'} analysts, consensus <b>{_e(str(a.get('rating') or 'n/a').title())}</b>"
        asof = f" (as of {_e(a['as_of'])})" if a.get("as_of") else ""
        analyst_row = (f"<tr><td>1. Analyst projection<br><span class=dim>{who}{asof}</span></td>"
                       f"<td class=n>{fmt.money(a['target_mean'])}</td><td class='n b'>{fmt.pct(a.get('upside'))}</td>"
                       f"<td class=n>{rng}</td></tr>")
    else:
        analyst_row = "<tr><td>1. Analyst projection</td><td class=n>n/a</td><td class=n>n/a</td><td></td></tr>"
    tool_row = (f"<tr><td>2. Tool projection<br><span class=dim>peer avg forward P/E &times; forward EPS</span></td>"
                f"<td class=n>{fmt.money(t.get('target'))}</td><td class='n b'>{fmt.pct(t.get('upside'))}</td>"
                f"<td class=n>{'tool vs analysts: ' + fmt.pct(a['tool_vs_analyst']) if a.get('tool_vs_analyst') is not None else ''}</td></tr>")
    pbx = t.get("pb_cross_check")
    pb_row = (f"<tr class=dim><td>Cross-check<br><span class=dim>peer avg P/B &times; book value/share</span></td>"
              f"<td class=n>{fmt.money(pbx['target'])}</td><td class=n>{fmt.pct(pbx['target'] / c['price'] - 1)}</td><td></td></tr>"
              if pbx else "")
    projections = f"""<table><tr><th>Projection</th><th class=n>Target</th><th class=n>Upside</th><th class=n>Range / gap</th></tr>
{analyst_row}{tool_row}{pb_row}</table>"""

    dc = res.get("drawdown_context") or {}
    if dc.get("stock_drawdown") is not None:
        prow = "".join(f"<tr><td>{_e(k)}</td><td class=n>{fmt.pct(v)}</td></tr>" for k, v in dc["peers"].items())
        dd_html = f"""<p>Worst fall on month-end closes: <b>{fmt.pct(dc['stock_drawdown'])}</b>, from {_e(dc['peak'])} to {_e(dc['trough'])}.
How the sector moved over <b>the same months</b>:</p>
<table><tr><th>Over {_e(dc['peak'])} &rarr; {_e(dc['trough'])}</th><th class=n>Move</th></tr>
<tr class=b><td>{_e(c['ticker'])} (this stock)</td><td class=n>{fmt.pct(dc['stock_drawdown'])}</td></tr>
{prow}
<tr><td>Peer average</td><td class=n>{fmt.pct(dc.get('peer_avg_same_window'))}</td></tr>
<tr><td>Sector index (peers, equal-weighted)</td><td class=n>{fmt.pct(dc.get('sector_same_window'))}</td></tr>
<tr class=b><td>Stock vs sector, same months</td><td class=n>{fmt.pct(dc.get('excess_vs_sector'))}</td></tr>
</table>
<p class=dim>Sector index's own worst fall: {fmt.pct(dc.get('sector_max_drawdown'))} ({_e(dc.get('sector_peak', ''))} &rarr; {_e(dc.get('sector_trough', ''))}).
A stock-vs-sector figure well below zero means the fall was mostly company-specific; near zero means the whole sector fell together.</p>"""
    else:
        dd_html = f"<p class=dim>Sector comparison not available ({_e(dc.get('error', 'no price history'))}).</p>"
    if dc.get("sector_error"):
        dd_html += f"<p class=dim>Sector index not available: {_e(dc['sector_error'])}.</p>"

    return f"""<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>{_e(c['ticker'])} research</title>
<style>
body{{font:15px/1.5 system-ui,Segoe UI,Arial,sans-serif;max-width:1000px;margin:24px auto;padding:0 16px;color:#1f2328;background:#fff}}
h1{{margin:0 0 4px}} h2{{margin-top:32px;border-bottom:1px solid #d0d7de;padding-bottom:4px}}
.dim{{color:#656d76;font-size:13px}} .call{{display:flex;gap:28px;flex-wrap:wrap;margin:20px 0;padding:16px 20px;border:1px solid #d0d7de;border-radius:8px}}
.call div span{{display:block;font-size:12px;color:#656d76;text-transform:uppercase;letter-spacing:.04em}}
.call div b{{font-size:24px}} small{{font-size:14px}} .rec{{color:{colour}}}
table{{border-collapse:collapse;width:100%;font-size:14px}} th,td{{padding:5px 8px;border-bottom:1px solid #eaeef2;text-align:left}}
th{{background:#f6f8fa;font-weight:600}} .n{{text-align:right;font-variant-numeric:tabular-nums}} .b{{font-weight:600}}
tr.grp td{{background:#f6f8fa;font-weight:600;padding-top:10px}} .wrap{{overflow-x:auto}}
blockquote{{margin:0;padding:12px 16px;border-left:4px solid {colour};background:#f6f8fa}}
</style></head><body>
<h1>{_e(c['name'])} <span class=dim>{_e(c['ticker'])}</span></h1>
<div class=dim>{f"Sector rank #{res['sector_rank']} of {res['sector_size']} &middot; " if res.get('sector_rank') else ''}{(_e(c['industry']) + ' &middot; ') if c.get('industry') else ''}{(_e(c['price_basis']) + ' &middot; ') if c.get('price_basis') else ''}scoring model: {_e(res['sector_model'])} &middot; data pulled {_e(c.get('fetched_at', ''))}</div>

<div class=call>
{rank_box} <div><span>Recommendation</span><b class=rec>{res['call']}</b>{'<small> (low confidence)</small>' if res.get('low_confidence') else ''}</div>
 <div><span>Weighted score</span><b>{res['weighted_score']:.1f}%</b></div>
 <div><span>Data coverage</span><b>{fmt.pct(res.get('data_coverage'), signed=False)}</b>{'<small> low confidence</small>' if res.get('low_confidence') else ''}</div>
 <div><span>Price</span><b>{fmt.money(c['price'])}</b></div>
 <div><span>Analyst target</span><b>{fmt.money(a.get('target_mean'))}</b></div>
 <div><span>Tool target</span><b>{fmt.money(t.get('target'))}</b></div>
 <div><span>Upside</span><b>{fmt.pct(t.get('upside'))}</b></div>
 <div><span>Downside (daily)</span><b>{fmt.pct(d.get('max_drawdown'))}</b></div>
</div>

<h2>Rationale</h2>
<blockquote>{_e(rationale)}</blockquote>
<p class=dim>{word_count} words &middot; {_e(rationale_note)}</p>

<h2>Projections</h2>
{projections}

<h2>Scorecard</h2>
<table><tr><th>Parameter</th><th class=n>Weight</th><th class=n>Score</th><th class=n>Weight &times; score (pts)</th></tr>
{score_rows}
<tr><td class=b>Weighted score</td><td class=n>100%</td><td></td><td class='n b'>{res['weighted_score']:.1f}%</td></tr></table>
<p class=dim>Call rule: &ge; {th['buy_at_or_above']:g}% Buy &middot; {th['hold_at_or_above']:g}% to {th['buy_at_or_above']:g}% Hold &middot; below {th['hold_at_or_above']:g}% Sell.
Weights used: {_e(weights)}.</p>

<h2>Every metric vs peers</h2>
<p class=dim>Metric score = peers beaten &divide; peers compared (beat 3 of 5 = 60%). A tie counts as half. Parameter score = average of its metric scores.</p>
<div class=wrap><table>
<tr><th>Metric</th><th class=n>{_e(c['ticker'].replace('.TO', ''))}</th>{peer_heads}<th class=n>Peer median</th><th class=n>Beats</th><th class=n>Score</th></tr>
{''.join(detail)}
</table></div>

<h2>How the tool's target is built</h2>
<p>Peer P/Es used:</p><ul>{''.join(tp_lines) or '<li>none</li>'}</ul>
{tp_calc}

<h2>Downside</h2>
<p>Five-year max drawdown on daily closes: {fmt.pct(d.get('max_drawdown'))}. If that fall repeated from today's price: {fmt.money(d.get('price_at_max_drawdown'))}.</p>
<p class=dim>The sector comparison below uses month-end closes, so its figure for this stock can be smaller than the daily one above: a fall that recovered within a month doesn't show up in month-end prices.</p>
<h3>Compared with the sector at the same time</h3>
{dd_html}

<h2>Flags and data notes</h2>
<ul>{flags}</ul>

<h2>My review</h2>
<p class=dim>For the showcase company: note where you checked a number against the annual report, and whether you agree with the call or override it, and why.</p>
</body></html>"""


def save(res, rationale, rationale_note, word_count, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    stem = f"{res['company']['ticker'].replace('.', '_')}_{date.today().isoformat()}"
    html_path = os.path.join(out_dir, stem + ".html")
    json_path = os.path.join(out_dir, stem + ".json")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_report(res, rationale, rationale_note, word_count))
    payload = dict(res, rationale=rationale, rationale_source=rationale_note)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    return html_path, json_path


def sector_console(results):
    lines = ["", "  SECTOR RANKING", "",
             "  #  Ticker     Score   Call   Price      Tool tgt   Upside   Analyst tgt  Upside   Downside",]
    for r in results:
        c, t, d = r["company"], r["target"], r["downside"]
        lines.append(f"  {r['sector_rank']:<2} {c['ticker']:<9} {r['weighted_score']:>5.1f}%  {r['call']:<5}  "
                     f"{fmt.money(c['price']):>9}  {fmt.money(t.get('target')):>9}  {fmt.pct(t.get('upside')):>7}  "
                     f"{fmt.money((r.get('analyst') or {}).get('target_mean')):>11}  {fmt.pct((r.get('analyst') or {}).get('upside')):>7}  "
                     f"{fmt.pct(d.get('max_drawdown')):>8}")
    return "\n".join(lines) + "\n"


def sector_html(results, links, title):
    rows = []
    for r in results:
        c, t, d = r["company"], r["target"], r["downside"]
        colour = CALL_COLOURS[r["call"]]
        ranked = sorted(r["params"].values(), key=lambda p: p["score"], reverse=True)
        best, worst = ranked[0], ranked[-1]
        rows.append(
            f"<tr><td class=n>{r['sector_rank']}</td>"
            f"<td><a href='{_e(links[c['ticker']])}'>{_e(c['name'])}</a> <span class=dim>{_e(c['ticker'])}</span></td>"
            f"<td class='n b'>{r['weighted_score']:.1f}%</td><td class=b style='color:{colour}'>{r['call']}</td>"
            f"<td class=n>{fmt.money(c['price'])}</td><td class=n>{fmt.money(t.get('target'))}</td>"
            f"<td class=n>{fmt.pct(t.get('upside'))}</td>"
            f"<td class=n>{fmt.money((r.get('analyst') or {}).get('target_mean'))}</td><td class=n>{fmt.pct((r.get('analyst') or {}).get('upside'))}</td>"
            f"<td class=n>{fmt.pct(d.get('max_drawdown'))}</td><td class=n>{fmt.pct((r.get('drawdown_context') or {}).get('excess_vs_sector'))}</td>"
            f"<td>{_e(best['label'])} ({best['score']:.0f}%)</td><td>{_e(worst['label'])} ({worst['score']:.0f}%)</td></tr>")
    params = list(results[0]["params"].keys())
    heads = "".join(f"<th class=n>{_e(results[0]['params'][k]['label'])}<br><span class=dim>{results[0]['params'][k]['weight']*100:.0f}%</span></th>" for k in params)
    grid = "".join(
        f"<tr><td>{_e(r['company']['ticker'])}</td>" +
        "".join(f"<td class=n>{r['params'][k]['score']:.0f}%</td>" for k in params) +
        f"<td class='n b'>{r['weighted_score']:.1f}%</td></tr>" for r in results)
    th = results[0]["thresholds"]
    by_note = {}
    for r in results:
        for f in r["flags"]:
            by_note.setdefault(f, []).append(r["company"]["ticker"].replace(".TO", ""))
    flags = [f"{', '.join(sorted(t)) if len(t) < len(results) else 'All'}: {f}" for f, t in sorted(by_note.items())]
    return f"""<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>{_e(title)}</title>
<style>
body{{font:15px/1.5 system-ui,Segoe UI,Arial,sans-serif;max-width:1100px;margin:24px auto;padding:0 16px;color:#1f2328;background:#fff}}
h2{{margin-top:32px;border-bottom:1px solid #d0d7de;padding-bottom:4px}} .dim{{color:#656d76;font-size:13px}}
table{{border-collapse:collapse;width:100%;font-size:14px}} th,td{{padding:6px 8px;border-bottom:1px solid #eaeef2;text-align:left;vertical-align:top}}
th{{background:#f6f8fa;font-weight:600}} .n{{text-align:right;font-variant-numeric:tabular-nums}} .b{{font-weight:600}} .wrap{{overflow-x:auto}}
a{{color:#0969da}}
</style></head><body>
<h1>{_e(title)}</h1>
<p class=dim>Each company is scored against all the others in the group. Call rule: &ge; {th['buy_at_or_above']:g}% Buy &middot; {th['hold_at_or_above']:g}&ndash;{th['buy_at_or_above']:g}% Hold &middot; below {th['hold_at_or_above']:g}% Sell. Click a name for its full report.</p>
<div class=wrap><table><tr><th class=n>#</th><th>Company</th><th class=n>Score</th><th>Call</th><th class=n>Price</th><th class=n>Tool target</th><th class=n>Tool upside</th><th class=n>Analyst target</th><th class=n>Analyst upside</th><th class=n>Downside</th><th class=n>DD vs sector</th><th>Strongest</th><th>Weakest</th></tr>
{''.join(rows)}</table></div>
<h2>Parameter scores</h2>
<div class=wrap><table><tr><th>Ticker</th>{heads}<th class=n>Weighted</th></tr>{grid}</table></div>
<h2>Data notes</h2><ul>{''.join(f'<li>{_e(f)}</li>' for f in flags) or '<li>None</li>'}</ul>
</body></html>"""
