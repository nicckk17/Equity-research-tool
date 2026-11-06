"""Graph report template: one self-contained HTML page per strategy x universe (all timeframes on one page).
Sections (always in this order, so every report reads the same way):
  1 Verdict table        per timeframe: baseline IS/OOS edge + luck-corrected p, Sharpe, portfolio vs index,
                         deflated Sharpe, walk-forward result
  2 Timeframes           baseline edge and avg R per timeframe, IS vs OOS
  3 Which knob matters   swing of the result as each knob moves alone (tornado)
  4 One knob at a time   small multiples: result vs knob value, IS and OOS
  5 Two knobs together   heatmaps for the pairs that move the result most, IS beside OOS
  6 Plateau              share of neighbours that hold up, for every graded config
  7 Equity + drawdown    real % portfolio (30 slots, 0.33% risk, costs) vs the index
  8 Monte Carlo          drawdown range from 3-month block bootstrap
  9 Year by year         R per year
 10 Trade distribution   net R per trade
 11 Monthly returns      portfolio % by month
 12 Walk-forward         picks per fold and stitched out-of-sample R
"""
from __future__ import annotations

import html
import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

PLOTLY = "https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.35.2/plotly.min.js"
COL = {"IS": "#3b6fd4", "OOS": "#d9822b", "HO": "#7a5cc7", "index": "#8a8f98", "pos": "#2f9e6e", "neg": "#d4533b"}


def _layout(fig, h=340, title=None):
    fig.update_layout(height=h, margin=dict(l=50, r=20, t=40 if title else 20, b=40), title=title,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="IBM Plex Sans, system-ui, sans-serif", size=12, color="#7f8c86"),
                      legend=dict(orientation="h", y=1.08, x=0))
    fig.update_xaxes(gridcolor="rgba(128,128,128,.18)", zeroline=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,.18)", zerolinecolor="rgba(128,128,128,.4)")
    return fig


def _div(fig):
    return fig.to_html(full_html=False, include_plotlyjs=False, config=dict(displaylogo=False, responsive=True))


def _table(df):
    return df.to_html(index=False, classes="tbl", border=0, na_rep="–", escape=True)


# ---------------------------------------------------------------- charts
def fig_timeframes(summary):
    f = go.Figure()
    for w in ("IS", "OOS"):
        f.add_bar(x=summary.tf, y=summary[f"{w}_edge"], name=f"{w} edge vs random (R/trade)", marker_color=COL[w])
    return _layout(f, 300)


def fig_tornado(imp):
    x = imp.sort_values("swing")
    f = go.Figure(go.Bar(x=x.swing, y=[f"{k} ({p})" for k, p in zip(x.knob, x.part)], orientation="h",
                         marker_color=COL["IS"], text=[f"best {b}" for b in x.best], textposition="outside"))
    return _layout(f, 60 + 34 * len(x), "How much each knob moves IS edge (max - min across its values)")


def fig_oat(curves_is, curves_oos, metric):
    ks = list(curves_is); n = len(ks); cols = 4; rows = int(np.ceil(n / cols))
    f = make_subplots(rows=rows, cols=cols, subplot_titles=ks, vertical_spacing=0.16, horizontal_spacing=0.07)
    for i, k in enumerate(ks):
        r, c = i // cols + 1, i % cols + 1
        for w, cur in (("IS", curves_is), ("OOS", curves_oos)):
            x = cur[k]; col = [cc for cc in x.columns if cc.endswith(metric)][0]
            f.add_scatter(x=[str(v) for v in x.index], y=x[col], mode="lines+markers", name=w, marker_color=COL[w],
                          showlegend=(i == 0), row=r, col=c)
    return _layout(f, 230 * rows)


def fig_heat(R, a, b, metric, w):
    x = R.pivot_table(index=a, columns=b, values=f"{w}_{metric}", aggfunc="mean")
    f = go.Figure(go.Heatmap(z=x.values, x=[str(v) for v in x.columns], y=[str(v) for v in x.index],
                             colorscale="RdBu", zmid=0, colorbar=dict(title=metric),
                             text=np.round(x.values, 3), texttemplate="%{text}"))
    f.update_xaxes(title=b); f.update_yaxes(title=a)
    return _layout(f, 320, f"{w}: {a} x {b}")


def fig_plateau(scores):
    f = go.Figure(go.Histogram(x=scores.dropna(), nbinsx=20, marker_color=COL["IS"]))
    f.update_xaxes(title="share of one-step neighbours keeping >= 70% of the edge"); f.update_yaxes(title="configs")
    return _layout(f, 280)


def fig_equity(port):
    f = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.68, 0.32], vertical_spacing=0.04)
    for w, p in port.items():
        if not p:
            continue
        cv = p["curve"]; f.add_scatter(x=cv.index, y=cv.values, name=f"strategy {w}", line_color=COL[w], row=1, col=1)
        if "index_curve" in p:
            ic = p["index_curve"]; f.add_scatter(x=ic.index, y=ic.values, name=f"index {w}", line=dict(color=COL["index"], dash="dot"), row=1, col=1)
        dd = cv / cv.cummax() - 1; f.add_scatter(x=dd.index, y=dd.values * 100, name=f"drawdown {w} %", line_color=COL[w], fill="tozeroy", showlegend=False, row=2, col=1)
    f.update_yaxes(title="growth of 1", row=1, col=1); f.update_yaxes(title="DD %", row=2, col=1)
    return _layout(f, 480)


def fig_mc(mc):
    f = go.Figure(go.Histogram(x=mc["dd_dist"] * 100, nbinsx=50, marker_color=COL["IS"]))
    for k, lab in (("dd_hist", "actual"), ("dd_p50", "median"), ("dd_p95", "worst 5%")):
        f.add_vline(x=mc[k], line_dash="dash", annotation_text=f"{lab} {mc[k]}%")
    f.update_xaxes(title="max drawdown % (block bootstrap)")
    return _layout(f, 280)


def fig_years(py):
    f = go.Figure(go.Bar(x=py.index.astype(str), y=py.R, marker_color=[COL["pos"] if v > 0 else COL["neg"] for v in py.R]))
    f.update_yaxes(title="net R")
    return _layout(f, 280)


def fig_dist(tr):
    f = go.Figure(go.Histogram(x=tr.rn.clip(-3, 8), nbinsx=60, marker_color=COL["IS"]))
    f.update_xaxes(title="net R per trade (clipped -3..8)")
    return _layout(f, 260)


def fig_monthly(curve):
    m = curve.resample("ME").last().pct_change().dropna() * 100
    t = pd.DataFrame(dict(y=m.index.year, mo=m.index.month, v=m.values)).pivot(index="y", columns="mo", values="v")
    f = go.Figure(go.Heatmap(z=t.values, x=["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"][:t.shape[1]],
                             y=t.index.astype(str), colorscale="RdYlGn", zmid=0, text=np.round(t.values, 1),
                             texttemplate="%{text}"))
    return _layout(f, max(260, 18 * len(t)))


def fig_wf(S):
    s = S.sort_values("xd"); cr = s.rn.cumsum()
    f = go.Figure(go.Scatter(x=pd.DatetimeIndex(s.xd), y=cr, line_color=COL["OOS"], name="stitched OOS R"))
    f.update_yaxes(title="cumulative net R")
    return _layout(f, 280)


# ---------------------------------------------------------------- page
FONTS = "https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;600&family=IBM+Plex+Mono:wght@400;500&display=swap"
CSS = """
/* layout: one reading column of section panels, verdict table first, charts below in the fixed report order */
:root{--bg:#f4f5f2;--card:#ffffff;--ink:#1d2321;--muted:#5f6b66;--line:#dde2dc;--acc:#2f6f5e;
--sans:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;--mono:"IBM Plex Mono",ui-monospace,Consolas,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#111614;--card:#18201d;--ink:#e3e8e5;--muted:#93a19a;--line:#28322e;--acc:#6fbfa6;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#111614;--card:#18201d;--ink:#e3e8e5;--muted:#93a19a;--line:#28322e;--acc:#6fbfa6;color-scheme:dark}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.55 var(--sans)}
main{max-width:1180px;margin:0 auto;padding-block:24px 60px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
h1{font-size:26px;margin:0 0 4px;text-wrap:balance}h2{font-size:15px;margin:0 0 4px;letter-spacing:.01em;text-wrap:balance}
.sub{color:var(--muted);margin:0 0 12px;max-width:80ch}
section{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:16px;margin:14px 0;overflow-x:auto;min-width:0}
.tbl{border-collapse:collapse;width:100%;font:12.5px/1.4 var(--mono);font-variant-numeric:tabular-nums}
.tbl th,.tbl td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
.tbl th:first-child,.tbl td:first-child{text-align:left}.tbl th{color:var(--muted);font-weight:500}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}.grid2>*{min-width:0}@media(max-width:760px){.grid2{grid-template-columns:1fr}}
.note{color:var(--muted);font-size:12.5px}.pill{display:inline-block;padding:1px 8px;border-radius:99px;border:1px solid var(--line);margin:2px 6px 2px 0;font:12px var(--mono)}
"""


def page(title, subtitle, sections, standalone=True, name=None):
    """standalone=True: full HTML file for opening on the PC. False: page body for publishing as an artifact
    (the publisher adds the document skeleton)."""
    body = "".join(f"<section><h2>{html.escape(h)}</h2><p class='sub'>{html.escape(s)}</p>{c}</section>"
                   for h, s, c in sections)
    head = (f"<title>{html.escape(name or title)}</title><meta name='claude:viewport-fit-sides' content='cover'>"
            f"<link rel='stylesheet' href='{FONTS}'><style>{CSS}</style><script src='{PLOTLY}'></script>")
    main = f"<main><h1>{html.escape(title)}</h1><p class='sub'>{html.escape(subtitle)}</p>{body}</main>"
    if not standalone:
        return head + main
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'>{head}</head>"
            f"<body>{main}</body></html>")
