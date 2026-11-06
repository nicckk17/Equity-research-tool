"""
Risk-free rate for the Sharpe ratio: the Bank of Canada's 3-month Treasury bill yield.

Pulled from the Bank of Canada's free Valet API (series V80691344, no key needed).
If the call fails (offline, site down), the tool falls back to the number in config.json.
"""
import json
import urllib.request

URL = "https://www.bankofcanada.ca/valet/observations/V80691344/json?recent=1"


def parse(payload):
    """Valet JSON -> (rate as a decimal e.g. 0.0238, date string). Raises ValueError if it looks wrong."""
    obs = payload["observations"][-1]
    pct = float(obs["V80691344"]["v"])
    if not 0 <= pct <= 15:
        raise ValueError(f"T-bill yield {pct}% looks wrong")
    return pct / 100, obs["d"]


def latest(timeout=10):
    """Fetch the latest 3-month T-bill yield. Returns (rate, date) or (None, error message)."""
    try:
        req = urllib.request.Request(URL, headers={"User-Agent": "equity-research-tool"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return parse(json.load(r))
    except Exception as e:  # offline, blocked, bad format: caller falls back to config.json
        return None, f"{type(e).__name__}: {e}"
