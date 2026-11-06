"""
Backtest: how accurate were analysts' 12-month price targets?

For each dated target:
  predicted return = target / price on the day it was issued - 1
  actual return    = price 12 months later / price on the issue day - 1
  target error     = price 12 months later / target - 1      (+ = stock beat the target)
  direction right? = predicted and actual returns have the same sign
  target reached?  = the stock traded at or above the target at any point within the 12 months

Usage:  python backtest_analysts.py data/analyst_targets_ATZ.json
"""
import json
import sys
from statistics import mean, median


def run(path):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    rows = []
    for p in d["predictions"]:
        pred = p["target"] / p["price_then"] - 1
        act = p["price_after"] / p["price_then"] - 1
        err = p["price_after"] / p["target"] - 1
        hi = d.get("max_high_in_window", {}).get(p["date"][:7])
        rows.append({**p, "pred": pred, "act": act, "err": err,
                     "direction_right": (pred > 0) == (act > 0),
                     "reached": (hi >= p["target"]) if hi else None})
    print(f"\n  Analyst target backtest: {d['ticker']}\n")
    print(f"  {'Issued':<11}{'Who':<28}{'Price':>8}{'Target':>8}{'Pred.':>8}{'12m later':>10}{'Actual':>8}{'Beat tgt':>9}")
    for r in rows:
        print(f"  {r['date']:<11}{r['who'][:27]:<28}{r['price_then']:>8.2f}{r['target']:>8.2f}{r['pred']*100:>+7.1f}%"
              f"{r['price_after']:>10.2f}{r['act']*100:>+7.1f}%{r['err']*100:>+8.1f}%")
    n = len(rows)
    print(f"\n  Predictions:            {n}")
    print(f"  Direction right:        {sum(r['direction_right'] for r in rows)} of {n}")
    print(f"  Target reached in 12m:  {sum(bool(r['reached']) for r in rows)} of {n}")
    print(f"  Avg predicted return:   {mean(r['pred'] for r in rows)*100:+.1f}%")
    print(f"  Avg actual return:      {mean(r['act'] for r in rows)*100:+.1f}%")
    print(f"  Median target error:    {median(r['err'] for r in rows)*100:+.1f}%  (price 12m later vs target)")
    print(f"  Avg absolute error:     {mean(abs(r['err']) for r in rows)*100:.1f}%\n")
    return rows


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "data/analyst_targets_ATZ.json")
