"""Has this idea been tested already?   python -m ta2 check macd histogram   |   python -m ta2 check "inside bar"

Searches: kept strategies (ta2/strategies), the rejected log (docs/REJECTED_LOG.md), every graded config
(docs/all_configs_tested.csv.gz) and the registry (86 strategies + 168 rejected 'not strategies').
All words must appear (case-insensitive) in the same entry.
"""
from __future__ import annotations
import re
from pathlib import Path
import pandas as pd
from . import config as C

DOCS = Path(__file__).resolve().parent / "docs"


def _hit(text, words):
    t = str(text).lower()
    return all(w in t for w in words)


def main(argv):
    words = [w.lower() for w in argv]
    if not words:
        print(__doc__); return
    found = 0
    log = (DOCS / "REJECTED_LOG.md").read_text(encoding="utf-8")
    for sec in re.split(r"\n(?=### )", log):
        if sec.startswith("### ") and _hit(sec, words):
            head = sec.splitlines()[0][4:]; verdict = next((l for l in sec.splitlines() if l.startswith("- Verdict")), "")
            print(f"[log] {head}\n      {verdict[:300]}"); found += 1
    for line in log.splitlines():
        if line.startswith("| ") and _hit(line, words):
            print(f"[simulation] {line[:300]}"); found += 1
    reg = C.REGISTRY
    if (reg / "strategies.csv").exists():
        s = pd.read_csv(reg / "strategies.csv", encoding="utf-8-sig")
        for _, r in s.iterrows():
            if _hit(" ".join(map(str, r.values)), words):
                print(f"[registry] {r['id']} {r['name']}"); found += 1
    if (reg / "not_strategies.csv").exists():
        n = pd.read_csv(reg / "not_strategies.csv", encoding="utf-8-sig")
        for _, r in n.iterrows():
            if _hit(" ".join(map(str, r.values)), words):
                print(f"[not a strategy] {' | '.join(map(str, r.values[:3]))[:250]}"); found += 1
    cfg = pd.read_csv(DOCS / "all_configs_tested.csv.gz")
    m = cfg[cfg.apply(lambda r: _hit(f"{r['key']} {r['name']}", words), axis=1)]
    if len(m):
        print(f"[configs] {len(m)} graded configs match, e.g.:")
        print(m.sort_values("edge_IS", ascending=False).head(10)[["key", "name", "n_IS", "avgR_IS", "edge_IS", "p_rw_IS", "avgR_OOS", "edge_OOS"]].round(3).to_string(index=False))
        found += len(m)
    print(f"\n{found} match(es)." + ("" if found else " Not found: looks new. Copy strategies/_template.py and run python -m ta2 test <KEY>."))
