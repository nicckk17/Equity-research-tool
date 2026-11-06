"""
AI Equity Research Tool

One company vs its peers:
    python research.py RY
    python research.py "Suncor Energy"
    python research.py CVE.TO --peers SU.TO,CNQ.TO,IMO.TO

Find the best in a sector (scores every company against the rest and ranks them):
    python research.py --sector canadian_banks
    python research.py --sector integrated_energy

Run from a hand-collected data file instead of Yahoo Finance:
    python research.py --data data/canadian_banks_2026-10-16.json

Add --ai to have Claude write the rationale (needs ANTHROPIC_API_KEY).
Reports go to the reports/ folder.
"""
import argparse
import json
import os
import sys
import webbrowser
from datetime import date

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from tool import analysis, crosscheck, data, peerfinder, rationale, report, riskfree, webdata  # noqa: E402


def load_cfg(live=True):
    """Read config.json. In live mode, also pull today's 3-month T-bill yield from the Bank of Canada."""
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    risk = cfg["risk"]
    risk["_rf_note"] = f"Risk-free rate {risk['risk_free_rate'] * 100:.2f}% (from config.json)"
    if live and risk.get("auto_risk_free", True):
        rate, info = riskfree.latest()
        if rate is not None:
            risk["risk_free_rate"] = rate
            risk["_rf_note"] = f"Risk-free rate {rate * 100:.2f}% (Bank of Canada 3-month T-bill, {info})"
        else:
            print(f"  ! Couldn't reach the Bank of Canada ({info}); using {risk['risk_free_rate'] * 100:.2f}% from config.json")
    print(f"  {risk['_rf_note']}")
    return cfg


def finish_snaps(snaps, cfg, do_crosscheck):
    """Record the risk-free source on each snapshot and optionally cross-check against TMX."""
    for s in snaps:
        s["notes"].append(cfg["risk"]["_rf_note"])
    if do_crosscheck:
        print("Cross-checking against TMX...")
        crosscheck.apply(snaps)


def run_sector(snaps, cfg, title, use_ai, open_browser, focus=None):
    results = analysis.rank_sector(snaps, cfg)
    stem = title.lower().replace(" ", "_")
    out_dir = os.path.join(ROOT, "reports", f"{stem}_{date.today().isoformat()}")
    links = {}
    for r in results:
        text, note, words = rationale.build(r, cfg, use_ai=use_ai)
        r["rationale"] = text
        html_path, _ = report.save(r, text, note, words, out_dir)
        links[r["company"]["ticker"]] = os.path.basename(html_path)
    index = os.path.join(out_dir, "index.html")
    with open(index, "w", encoding="utf-8") as f:
        f.write(report.sector_html(results, links, title))
    if focus:
        f = next((r for r in results if r["company"]["ticker"] == focus), None)
        if f:
            print(report.console_summary(f, f["rationale"]))
            print(f"  Report: {os.path.join(out_dir, links[focus])}")
    print(report.sector_console(results))
    best = results[0]
    print(f"  Best in sector: {best['company']['name']} — {best['call']}, score {best['weighted_score']:.1f}%")
    print("  " + best["rationale"] + "\n")
    print(f"  Sector report: {index}\n")
    if open_browser:
        webbrowser.open("file://" + os.path.abspath(index))


def main():
    ap = argparse.ArgumentParser(description="Score stocks against their peers and return Buy/Hold/Sell.")
    ap.add_argument("company", nargs="*", help="Ticker (RY, RY.TO) or company name")
    ap.add_argument("--peers", help="Comma-separated peer tickers, overrides peers.json")
    ap.add_argument("--sector", help="Rank every company in a peer group from peers.json, e.g. canadian_banks")
    ap.add_argument("--data", help="Use a hand-collected data file instead of Yahoo Finance (ranks the whole file)")
    ap.add_argument("--ai", action="store_true", help="Have Claude write the rationale (needs ANTHROPIC_API_KEY)")
    ap.add_argument("--crosscheck", action="store_true",
                    help="Compare Yahoo's numbers with TMX and flag disagreements (needs openbb-core + openbb-tmx)")
    ap.add_argument("--no-open", action="store_true", help="Don't open the report in the browser")
    args = ap.parse_args()
    cfg = load_cfg(live=not args.data)

    if args.data:
        snaps = webdata.load_snapshots(args.data, cfg)
        with open(args.data, encoding="utf-8") as f:
            focus = json.load(f).get("focus")
        if args.company:
            q = " ".join(args.company).upper()
            focus = next((s["ticker"] for s in snaps if s["ticker"] in (q, q + ".TO")), focus)
        title = os.path.splitext(os.path.basename(args.data))[0].rsplit("_", 1)[0].replace("_", " ").title()
        run_sector(snaps, cfg, title, args.ai, not args.no_open, focus)
        return

    if args.sector:
        with open(os.path.join(ROOT, "peers.json"), encoding="utf-8") as f:
            groups = json.load(f)
        if args.sector not in groups:
            sys.exit(f"No group '{args.sector}' in peers.json. Options: "
                     + ", ".join(k for k in groups if not k.startswith("_")))
        snaps = []
        for t in groups[args.sector]:
            print(f"Researching {t}...")
            try:
                snaps.append(data.fetch_snapshot(t, cfg))
            except Exception as e:
                print(f"  ! skipped {t}: {e}")
        if len(snaps) < 3:
            sys.exit("Need at least 3 companies with data to rank a sector.")
        finish_snaps(snaps, cfg, args.crosscheck)
        run_sector(snaps, cfg, args.sector.replace("_", " ").title(), args.ai, not args.no_open)
        return

    if not args.company:
        ap.error("give a company, --sector, or --data")
    query = " ".join(args.company)
    print(f"Looking up '{query}'...")
    ticker = data.resolve_ticker(query, cfg["default_exchange_suffix"])
    auto_note = None
    try:
        peers = data.find_peers(ticker, cfg, args.peers.split(",") if args.peers else None)
    except ValueError as not_listed:
        try:
            peers, why = peerfinder.suggest(ticker, cfg["max_peers"])
        except Exception as e:
            sys.exit(f"{not_listed}\n(Auto-pick also failed: {type(e).__name__}: {e}. "
                     f"Install it with: pip install financedatabase)")
        auto_note = (f"Peers auto-picked from FinanceDatabase ({why}): {', '.join(peers)}. "
                     f"Check they make sense, or pass your own with --peers.")
        print("  " + auto_note)

    print(f"Researching {ticker} and peers {', '.join(peers)}...")
    company = data.fetch_snapshot(ticker, cfg)
    peer_snaps = []
    for p in peers:
        try:
            peer_snaps.append(data.fetch_snapshot(p, cfg))
        except Exception as e:
            print(f"  ! skipped peer {p}: {e}")
    if len(peer_snaps) < 2:
        sys.exit("Need at least 2 peers with data to score against. Try --peers.")
    if auto_note:
        company["notes"].append(auto_note)
    finish_snaps([company] + peer_snaps, cfg, args.crosscheck)

    res = analysis.analyze(company, peer_snaps, cfg)
    text, note, words = rationale.build(res, cfg, use_ai=args.ai)
    print(report.console_summary(res, text))
    html_path, json_path = report.save(res, text, note, words, os.path.join(ROOT, "reports"))
    print(f"  Report: {html_path}\n  Data:   {json_path}\n")
    if not args.no_open:
        webbrowser.open("file://" + os.path.abspath(html_path))


if __name__ == "__main__":
    main()
