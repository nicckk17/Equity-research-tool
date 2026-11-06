"""python -m ta3 <command>

  data import [--universe TSX|US]           copy ta2 daily CSVs into the local Parquet store
  data intraday [--universe] [--interval 60m] [--source yahoo|alpaca]   download intraday bars (run on your PC)
  data quality [--universe] [--tf D]        data-quality score per symbol
  run S53 [--universe TSX] [--tf D,W,1h] [--parts oat,pairs,grid] [--workers N] [--max-grid 600]
                                            full pipeline -> results/ta3/S53_TSX/report.html
  sweep S53 --tf D                          sweep only
  trials                                    global count of configs ever graded
  research new|list|approve|code|log|example   rule-card pipeline (see ta3/research.py)
"""
import argparse
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ta3"); sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("data"); d.add_argument("what", choices=["import", "intraday", "quality", "catalogue"])
    d.add_argument("--universe", default="TSX"); d.add_argument("--tf", default="D")
    d.add_argument("--interval", default="60m"); d.add_argument("--source", default="yahoo")
    for name in ("run", "sweep"):
        p = sub.add_parser(name); p.add_argument("key"); p.add_argument("--universe", default="TSX")
        p.add_argument("--tf", default=None); p.add_argument("--parts", default="oat,pairs,grid")
        p.add_argument("--workers", type=int, default=None); p.add_argument("--max-grid", type=int, default=600)
        p.add_argument("--reuse", action="store_true", help="rebuild the report from saved sweeps")
    sub.add_parser("trials")
    r = sub.add_parser("research"); r.add_argument("what", choices=["new", "list", "approve", "code", "log", "example"])
    r.add_argument("arg", nargs="?"); r.add_argument("--verdict", default="")
    a = ap.parse_args(argv)
    if a.cmd == "data":
        from . import store as S
        if a.what == "import":
            print(S.import_ta2(a.universe).rows.sum(), "rows stored")
        elif a.what == "intraday":
            print(S.intraday_update(a.universe, a.source, a.interval))
        elif a.what == "quality":
            print(S.quality_report(a.universe, a.tf).to_string(index=False))
        else:
            print(S.catalogue().to_string(index=False))
    elif a.cmd == "run":
        from .run import run
        run(a.key, a.universe, a.tf.split(",") if a.tf else None, tuple(a.parts.split(",")), a.workers, a.max_grid, reuse=a.reuse)
    elif a.cmd == "sweep":
        from .sweep import sweep
        for tf in (a.tf or "D").split(","):
            sweep(a.key, a.universe, tf, tuple(a.parts.split(",")), a.workers, max_grid=a.max_grid)
    elif a.cmd == "research":
        from . import research as RS
        import json
        if a.what == "new":
            print(json.dumps(RS.new(a.arg), indent=2)[:3000])
        elif a.what == "list":
            print(RS.listing().to_string(index=False))
        elif a.what == "approve":
            RS.set_status(a.arg, "approved", "approved by Nik"); print(a.arg, "approved")
        elif a.what == "code":
            print("written:", RS.code(a.arg))
        elif a.what == "log":
            from . import config as C
            RS.log(a.arg, a.verdict, C.RESULTS / f"{a.arg}_TSX" / "summary.csv"); print("logged")
        else:
            print(json.dumps(RS.EXAMPLE_CARD, indent=2))
    elif a.cmd == "trials":
        from .sweep import total_trials
        print(total_trials())


if __name__ == "__main__":
    sys.exit(main())
