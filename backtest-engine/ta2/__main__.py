"""ta2 command line.
  python -m ta2 test <KEY> [--universe US] [--holdout] [--steps ...]   honest backtest (see ta2/test.py)
  python -m ta2 portfolio <KEY> [args]                                 S45 / S43 / S64 portfolio strategies
  python -m ta2 check <words...>                                        has this idea been tested? (registry + rejected log)
  python -m ta2 list                                                    kept strategies, tiers, evidence
  python -m ta2 data update [--universe US] [--only SYM,SYM]            refresh Yahoo bars + earnings
  python -m ta2 bot <plan|run|sync|report|close-check> [--submit]       trading bot: IB paper orders (see ta2/bot.py)
  python -m ta2 live <scan|fill|status|self-test> ...                   older manual scanner (writes an order list only)
"""
import sys


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__); return
    cmd, rest = sys.argv[1], sys.argv[2:]
    if cmd == "test":
        from .test import main as m; m(rest)
    elif cmd == "portfolio":
        from .strategies import get
        mod = get(rest[0]); sys.argv = [rest[0]] + rest[1:]; mod.main()
    elif cmd == "check":
        from .check import main as m; m(rest)
    elif cmd == "list":
        from .strategies import STRATS, PORTFOLIO, get
        for k in list(STRATS) + list(PORTFOLIO):
            mod = get(k); print(f"{k:5} {getattr(mod, 'TIER', '?'):8} {getattr(mod, 'EVIDENCE', '')}\n")
    elif cmd == "data":
        import argparse
        from . import data as D
        ap = argparse.ArgumentParser(prog="ta2 data"); ap.add_argument("action", choices=["update"])
        ap.add_argument("--universe", default="TSX"); ap.add_argument("--only")
        a = ap.parse_args(rest)
        print(D.update(a.universe, a.only.split(",") if a.only else None).to_string(index=False))
    elif cmd == "bot":
        from .bot import main as m; m(rest)
    elif cmd == "live":
        from .live import main as m; m(rest)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
