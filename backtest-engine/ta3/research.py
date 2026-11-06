"""Self-research loop: source -> rule card -> duplicate check -> (Nik approves) -> strategy file -> ta3 run -> log.

The finding/reading half runs in Claude with Nik's skills (webgrab for sites and search, reel-reader for
Instagram, youtube-channel-learner for YouTube, firecrawl research search for papers). Claude writes what it
learns as a RULE CARD (JSON) into research/cards/. Everything after that is this module:

  python -m ta3 research new  card.json        add a card (status "new"), runs the duplicate check
  python -m ta3 research list                  queue with status
  python -m ta3 research approve <KEY>         Nik's gate: only approved cards get coded
  python -m ta3 research code <KEY>            writes ta3/strategies/<key>.py from the card (KNOBS filled in;
                                               raw_signals() body is drafted by the local coder model from
                                               the card's rule text, then reviewed by Claude)
  python -m ta3 run <KEY> --tf D,W             test; then research log <KEY> records the verdict

Card fields: key, name, source{type,url,author,ids}, market, timeframes[], side, entry, stop, exit,
filters[], knobs{name:{default,values,part,label}}, claims (what the source says it returns), notes.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd

from . import config as C

CARDS = C.ROOT / "research" / "cards"
LOG = C.ROOT / "research" / "research_log.csv"
REQUIRED = ["key", "name", "source", "timeframes", "side", "entry", "stop", "exit", "knobs"]


def _path(key):
    return CARDS / f"{key.upper()}.json"


def validate(card):
    miss = [k for k in REQUIRED if k not in card or card[k] in (None, "", [], {})]
    if miss:
        raise ValueError(f"card missing: {miss}")
    for k, v in card["knobs"].items():
        if "default" not in v or "values" not in v:
            raise ValueError(f"knob {k} needs default and values")
    return card


def duplicate_check(card) -> str:
    """Runs ta2's checker on the card's name words; returns its text (empty = looks new)."""
    words = [w for w in re.findall(r"[a-zA-Z0-9]+", card["name"].lower()) if len(w) > 2][:4]
    r = subprocess.run([sys.executable, "-m", "ta2", "check", *words], capture_output=True, text=True,
                       cwd=str(C.ROOT))
    return r.stdout


def new(card_file):
    card = validate(json.loads(Path(card_file).read_text(encoding="utf-8")))
    card.setdefault("status", "new")
    dup = duplicate_check(card)
    card["duplicate_check"] = dup[-1500:]
    CARDS.mkdir(parents=True, exist_ok=True)
    _path(card["key"]).write_text(json.dumps(card, indent=2), encoding="utf-8")
    return card


def listing():
    rows = []
    for f in sorted(CARDS.glob("*.json")):
        c = json.loads(f.read_text(encoding="utf-8"))
        rows.append(dict(key=c["key"], name=c["name"], status=c.get("status"), source=c["source"].get("author", ""),
                         tfs=",".join(c["timeframes"]), dup="match" if "0 match" not in c.get("duplicate_check", "0 match") else "new"))
    return pd.DataFrame(rows)


def set_status(key, status, note=""):
    p = _path(key); c = json.loads(p.read_text(encoding="utf-8")); c["status"] = status
    if note:
        c.setdefault("history", []).append(f"{pd.Timestamp.now():%Y-%m-%d} {status}: {note}")
    p.write_text(json.dumps(c, indent=2), encoding="utf-8")
    return c


TEMPLATE = '''"""{key} {name}. Source: {src}. Generated from research card {key}.json ({date}).
Entry: {entry}
Stop:  {stop}
Exit:  {exit}
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..knobs import Knob
from ta2.strategies.common import EXIT_PANEL

KEY = "{key}"
NAME = "{name}"
SIDE = {side}
TIMEFRAMES = {tfs}

KNOBS = {{
{knobs}
}}
SIGNAL_KNOBS = {signal_knobs}


def raw_signals(df, ctx, k):
    """Rows: t (signal bar), side, anchor (stop anchor price), A (ATR at t), opp (target price or NaN),
    plus one bool column per filter knob. Must use data up to bar t's close only."""
    raise NotImplementedError("draft from the card's entry rule")


def signals(raw, k):
    m = np.ones(len(raw), bool)
    for f in [n for n, kn in KNOBS.items() if kn.part == "filter"]:
        if k[f] is True and f in raw:
            m &= raw[f].to_numpy(bool)
    return raw[m]


def lines(df, ctx, k):
    return {{}}


def exit_recipe(k):
    e = k.get("exit", "2R")
    return dict(EXIT_PANEL[e]) if e in EXIT_PANEL else dict(target_R=2.0, max_hold=60)
'''


def code(key):
    """Write the strategy file skeleton from an approved card."""
    c = json.loads(_path(key).read_text(encoding="utf-8"))
    if c.get("status") != "approved":
        raise RuntimeError(f"{key} is '{c.get('status')}': Nik approves cards before they are coded")
    kn = "\n".join(f'    "{n}": Knob({v["default"]!r}, {v["values"]!r}, "{v.get("part", "signal")}", "{v.get("label", n)}"),'
                   for n, v in c["knobs"].items())
    sk = tuple(n for n, v in c["knobs"].items() if v.get("part", "signal") == "signal")
    src = c["source"].get("url") or c["source"].get("author", "")
    txt = TEMPLATE.format(key=c["key"].upper(), name=c["name"], src=src, date=pd.Timestamp.now().date(),
                          entry=c["entry"], stop=c["stop"], exit=c["exit"], side=1 if c["side"] in (1, "long") else -1,
                          tfs=c["timeframes"], knobs=kn, signal_knobs=sk)
    p = Path(__file__).resolve().parent / "strategies" / f"{c['key'].lower()}.py"
    p.write_text(txt, encoding="utf-8")
    set_status(key, "coded", str(p.name))
    return p


def log(key, verdict, summary_csv=None):
    """Record the tested verdict (keep / weak / reject) with the headline numbers."""
    row = dict(when=pd.Timestamp.now().isoformat(timespec="seconds"), key=key, verdict=verdict)
    if summary_csv and Path(summary_csv).exists():
        s = pd.read_csv(summary_csv)
        for _, r in s.iterrows():
            row[f"{r.tf}_OOS_edge"] = r.get("OOS_edge"); row[f"{r.tf}_OOS_p_rw"] = r.get("OOS_p_rw")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([row]).to_csv(LOG, mode="a", header=not LOG.exists(), index=False)
    set_status(key, "tested", verdict)


EXAMPLE_CARD = {
    "key": "BB200", "name": "Bollinger band mean reversion with 200 SMA trend filter",
    "source": {"type": "instagram", "author": "omomomentum_de", "url": "", "ids": []},
    "market": "NAS100 (taught); test TSX60 + US100", "timeframes": ["1h", "D"], "side": "long",
    "entry": "close below lower Bollinger band (20, 2) while close above 200 SMA; buy next open",
    "stop": "recent swing low minus buf x ATR", "exit": "close back above the middle band, or time stop",
    "filters": ["trend200"],
    "knobs": {"bb_len": {"default": 20, "values": [10, 15, 20, 30], "part": "signal"},
              "bb_k": {"default": 2.0, "values": [1.5, 2.0, 2.5], "part": "signal"},
              "trend200": {"default": True, "values": [False, True], "part": "filter"},
              "buf": {"default": 0.5, "values": [0.1, 0.5, 1.0], "part": "stop"},
              "exit": {"default": "time10", "values": ["time5", "time10", "2R", "trail2atr"], "part": "exit"},
              "mode": {"default": 1, "values": [0, 1], "part": "entry"}},
    "claims": "reel shows positive NAS100 backtest", "notes": "see project note bollinger-trend-filter-strategy",
}
