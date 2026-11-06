"""
Offline checks with made-up numbers — no internet needed.
Run:  python -m pytest tests     (or just: python tests/test_offline.py)
"""
import json
import math
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tool import analysis, calcs, rationale, report  # noqa: E402

CFG = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))


def test_cagr():
    assert abs(calcs.cagr(100, 133.1, 3) - 0.10) < 1e-9          # 10% a year for 3 years
    assert calcs.cagr(-5, 10, 3) is None                          # from a loss: not meaningful


def test_max_drawdown():
    p = pd.Series([100, 120, 90, 110, 60, 130], index=pd.date_range("2024-01-01", periods=6))
    assert abs(calcs.max_drawdown(p) - (60 / 120 - 1)) < 1e-12    # peak 120 -> trough 60 = -50%


def test_beta_of_index_against_itself_is_one():
    idx = pd.date_range("2021-01-01", periods=60, freq="MS")
    rng = np.random.default_rng(1)
    m = pd.Series(100 * np.cumprod(1 + rng.normal(0.006, 0.04, 60)), index=idx)
    assert abs(calcs.beta(m, m) - 1) < 1e-9
    double = pd.Series(100 * np.cumprod(1 + 2 * m.pct_change().fillna(0)), index=idx)
    assert abs(calcs.beta(double, m) - 2) < 1e-9


def test_metric_scoring():
    # beats 3 of 4 peers on a higher-is-better metric -> 75%
    s, beats, n = analysis.score_metric("roe", 0.15, [0.10, 0.12, 0.14, 0.18], "higher")
    assert (s, beats, n) == (75.0, 3, 4)
    # lower-is-better, one tie -> beats 1.5 of 3 -> 50%
    s, beats, _ = analysis.score_metric("pb", 1.5, [1.2, 1.5, 1.8], "lower")
    assert (s, beats) == (50.0, 1.5)
    # negative P/E (losing money) ranks worst, not cheapest
    s, _, _ = analysis.score_metric("pe_trailing", -8, [10, 12], "lower")
    assert s == 0.0


def _snap(ticker, **kw):
    base = dict(ticker=ticker, name=ticker, sector="bank", price=100.0, notes=[],
                pe_trailing=12, pe_forward=11, pb=1.6, ev_ebitda=None, net_margin=0.28, operating_margin=0.35,
                roe=0.14, debt_to_equity=None, fcf_yield=None, revenue_cagr_3y=0.06, eps_cagr_3y=0.05,
                beta=0.9, sharpe=0.5, max_drawdown=-0.30, dividend_yield=0.045, payout_ratio=0.50,
                cet1_ratio=0.133, eps_forward=100 / 11, book_value_per_share=100 / 1.6)
    base.update(kw)
    return base


def test_full_bank_run():
    co = _snap("AAA.TO", name="Sample Bank", price=150.0, pe_trailing=14, pe_forward=13, pb=2.1, roe=0.16,
               eps_forward=150 / 13, book_value_per_share=150 / 2.1, cet1_ratio=0.135,
               revenue_cagr_3y=0.08, eps_cagr_3y=0.07, beta=0.85, sharpe=0.7, max_drawdown=-0.25,
               dividend_yield=0.038, payout_ratio=0.48)
    peers = [_snap("BBB.TO", pe_forward=10, pb=1.3, roe=0.12, cet1_ratio=0.130),
             _snap("CCC.TO", pe_forward=11, pb=1.5, roe=0.13, cet1_ratio=0.143),
             _snap("DDD.TO", pe_forward=12, pb=1.8, roe=0.15, cet1_ratio=0.134),
             _snap("EEE.TO", pe_forward=80, pb=1.4, roe=0.11, cet1_ratio=0.131)]   # 80x = outlier, dropped
    res = analysis.analyze(co, peers, CFG)

    # Weights follow the bank model and sum to 1
    assert abs(sum(p["weight"] for p in res["params"].values()) - 1) < 1e-9
    # EV/EBITDA is not used for banks; CET1 is
    assert "ev_ebitda" not in [r["metric"] for r in res["params"]["valuation"]["metrics"]]
    assert [r["metric"] for r in res["params"]["balance_sheet"]["metrics"]] == ["cet1_ratio"]
    # Valuation: P/E 14 vs peers 12 -> beats 0; P/B 2.1 vs 1.3-1.8 -> beats 0 -> 0%
    assert res["params"]["valuation"]["score"] == 0.0
    # Target: avg of 10, 11, 12 (80 dropped) = 11 x forward EPS 150/13
    assert res["target"]["peer_pes_dropped"] == {"EEE.TO": 80}
    assert abs(res["target"]["target"] - 11 * 150 / 13) < 1e-9
    # Weighted score is the sum of contributions
    assert abs(res["weighted_score"] - sum(p["contribution"] for p in res["params"].values())) < 1e-9
    # Call matches the threshold rule
    assert res["call"] == analysis.recommendation(res["weighted_score"], CFG["thresholds"])

    text, note, words = rationale.build(res, CFG)
    assert 60 <= words <= 150, words
    html = report.html_report(res, text, note, words)
    assert "Sample Bank" in html and res["call"] in html
    return res, text


def test_sector_ranking_and_web_data():
    from tool import webdata
    path = os.path.join(ROOT, "data", "canadian_banks_2026-10-16.json")
    snaps = webdata.load_snapshots(path, CFG)
    res = analysis.rank_sector(snaps, CFG)
    assert [r["sector_rank"] for r in res] == list(range(1, len(res) + 1))
    assert all(res[i]["weighted_score"] >= res[i + 1]["weighted_score"] for i in range(len(res) - 1))
    for r in res:   # weighted score = sum of weight x score
        assert abs(r["weighted_score"] - sum(p["weight"] * p["score"] for p in r["params"].values())) < 1e-9


def test_energy_weights():
    co = _snap("XXX.TO", sector="energy", ev_ebitda=5, debt_to_equity=0.4, fcf_yield=0.09, cet1_ratio=None)
    peers = [_snap(t, sector="energy", ev_ebitda=e, debt_to_equity=0.5, fcf_yield=0.07, cet1_ratio=None)
             for t, e in [("P1.TO", 4), ("P2.TO", 6), ("P3.TO", 7)]]
    res = analysis.analyze(co, peers, CFG)
    assert res["weights"]["balance_sheet"] == 0.25 and res["weights"]["risk"] == 0.15 and res["weights"]["growth"] == 0.05



# ---------------------------------------------------------------- data layer with a fake Yahoo
def test_fetch_snapshot_with_fake_yahoo():
    import types
    idx = pd.bdate_range(end=pd.Timestamp.today(), periods=1260, tz="America/Toronto")
    rng = np.random.default_rng(7)

    def series(drift):
        return pd.Series(100 * np.cumprod(1 + rng.normal(drift, 0.01, len(idx))), index=idx)

    years = pd.to_datetime(["2022-10-31", "2023-10-31", "2024-10-31", "2025-10-31"])
    inc = pd.DataFrame({y: [r, e] for y, r, e in zip(years, [50e9, 52e9, 56e9, 60e9], [11.0, 11.5, 12.4, 13.2])},
                       index=["Total Revenue", "Diluted EPS"])[years[::-1]]   # Yahoo lists newest first
    divs = pd.Series([1.5, 1.5, 1.6, 1.6], index=pd.DatetimeIndex(
        [pd.Timestamp.today(tz="America/Toronto") - pd.Timedelta(days=d) for d in (300, 210, 120, 30)]))

    class FakeTicker:
        def __init__(self, sym):
            self.sym = sym
            self.info = {"longName": "Fake Bank", "currentPrice": 150.0, "marketCap": 2e11, "trailingPE": 15.0,
                         "forwardPE": 13.0, "priceToBook": 2.0, "profitMargins": 0.3, "operatingMargins": 0.4,
                         "returnOnEquity": 0.15, "debtToEquity": None, "freeCashflow": None,
                         "industry": "Banks - Diversified", "sector": "Financial Services",
                         "currency": "CAD", "financialCurrency": "CAD"}
            self.income_stmt = inc
            self.dividends = divs.copy()

        def history(self, period="5y", auto_adjust=True):
            return pd.DataFrame({"Close": series(0.0006 if self.sym != "^GSPTSE" else 0.0004)})

    fake = types.ModuleType("yfinance")
    fake.Ticker = FakeTicker
    sys.modules["yfinance"] = fake
    try:
        from tool import data
        data._benchmark_cache.clear()
        s = data.fetch_snapshot("RY.TO", CFG)
    finally:
        del sys.modules["yfinance"]

    assert s["sector"] == "bank" and s["cet1_ratio"] == 0.135
    assert abs(s["eps_forward"] - 150 / 13) < 1e-9 and abs(s["eps_ttm"] - 10) < 1e-9
    assert abs(s["revenue_cagr_3y"] - ((60 / 50) ** (1 / 3) - 1)) < 1e-9
    assert abs(s["eps_cagr_3y"] - ((13.2 / 11.0) ** (1 / 3) - 1)) < 1e-9
    assert abs(s["dividend_yield"] - 6.2 / 150) < 1e-9 and abs(s["payout_ratio"] - 0.62) < 1e-9
    assert s["beta"] is not None and s["sharpe"] is not None and -1 < s["max_drawdown"] <= 0
    assert abs(s["book_value_per_share"] - 75) < 1e-9

def test_riskfree_parse():
    from tool import riskfree
    # shape copied from a real Bank of Canada response (2026-10-21)
    rate, d = riskfree.parse({"seriesDetail": {}, "observations": [{"d": "2026-10-14", "V80691344": {"v": "2.38"}}]})
    assert abs(rate - 0.0238) < 1e-12 and d == "2026-10-14"
    try:
        riskfree.parse({"observations": [{"d": "x", "V80691344": {"v": "238"}}]})
        assert False, "should reject a yield of 238%"
    except ValueError:
        pass


def test_peerfinder_picks_same_industry_and_drops_preferreds():
    from tool import peerfinder
    rows = {
        "SU.TO":     ("Oil, Gas & Fuels", "Energy Production", "Large Cap", "TOR"),
        "CVE.TO":    ("Oil, Gas & Fuels", "Energy Production", "Large Cap", "TOR"),
        "CNQ.TO":    ("Oil, Gas & Fuels", "Energy Production", "Mega Cap", "TOR"),
        "IMO.TO":    ("Oil, Gas & Fuels", "Energy Production", "Large Cap", "TOR"),
        "TOU.TO":    ("Oil, Gas & Fuels", "Energy Production", "Mid Cap", "TOR"),
        "ENB-PA.TO": ("Oil, Gas & Fuels", "Energy Production", "Large Cap", "TOR"),   # preferred share
        "XOM":       ("Oil, Gas & Fuels", "Energy Production", "Mega Cap", "NYQ"),     # other exchange
        "RY.TO":     ("Banks", "Banking", "Mega Cap", "TOR"),                           # other industry
    }
    df = pd.DataFrame.from_dict(rows, orient="index", columns=["industry", "industry_group", "market_cap", "exchange"])
    peers, why = peerfinder.pick(df, "SU.TO", 3)
    assert set(peers) == {"CVE.TO", "IMO.TO", "CNQ.TO"}, peers          # same-size first, then next closest
    assert "ENB-PA.TO" not in peers and "XOM" not in peers and "RY.TO" not in peers
    assert "Oil, Gas & Fuels" in why


def test_crosscheck_flags_only_real_gaps():
    from tool import crosscheck
    snap = {"price": 150.0, "market_cap": 2.1e11, "pe_trailing": 14.0, "pb": 2.0, "dividend_yield": 0.040, "roe": 0.15}
    ok = {"price": 150.5, "market_cap": 2.12e11, "pe_trailing": 14.5, "pb": 2.05, "dividend_yield": 0.042, "roe": 0.16}
    assert crosscheck.compare(snap, ok) == []
    bad = dict(ok, pe_trailing=18.0, dividend_yield=0.055)
    out = crosscheck.compare(snap, bad)
    assert len(out) == 2 and any("P/E" in o for o in out) and any("Dividend yield" in o for o in out)
    view = crosscheck.tmx_view({"last_price": "150.5", "pe": 14.5, "div_yield": 0.042})
    assert view["price"] == 150.5 and view["market_cap"] is None


def test_crosscheck_apply_fails_soft_without_package():
    from tool import crosscheck
    snaps = [{"ticker": "RY.TO", "notes": []}]
    crosscheck.apply(snaps)          # openbb-tmx not installed here: must print a skip message, not crash
    assert snaps[0]["notes"] == []


# ---- Regression tests for the 2 Nov 2026 code review fixes ----

def test_fix1_zero_debt_is_best_negative_equity_is_worst():
    s, _, _ = analysis.score_metric("debt_to_equity", 0, [0.2, 0.5], "lower")
    assert s == 100.0                                   # debt-free beats every indebted peer
    s, _, _ = analysis.score_metric("debt_to_equity", -0.3, [0.2, 0.5], "lower")
    assert s == 0.0                                     # negative equity ranks worst
    s, _, _ = analysis.score_metric("payout_ratio", -0.4, [0.4, 0.6], "lower")
    assert s == 0.0                                     # dividend paid out of losses ranks worst


def _energy_group(**company_kw):
    base = dict(sector="energy", pe_trailing=10, pe_forward=9, pb=1.5, ev_ebitda=5, net_margin=0.1,
                operating_margin=0.15, roe=0.12, debt_to_equity=0.4, fcf_yield=0.06, revenue_cagr_3y=0.05,
                eps_cagr_3y=0.05, beta=1.1, sharpe=0.4, max_drawdown=-0.4, dividend_yield=0.04,
                payout_ratio=0.5, dps_ttm=1.0, eps_forward=10, book_value_per_share=60)
    co = _snap("AAA.TO", **dict(base, **company_kw))
    peers = [_snap("BBB.TO", **dict(base, debt_to_equity=0.8, fcf_yield=0.08)),
             _snap("CCC.TO", **dict(base, debt_to_equity=0.9, fcf_yield=0.09))]
    return co, peers


def test_fix2_missing_metric_is_flagged_and_lowers_coverage():
    co, peers = _energy_group(fcf_yield=None)
    res = analysis.analyze(co, peers, CFG)
    bs = res["params"]["balance_sheet"]
    assert bs["coverage"] == 0.5 and bs["score"] == 100.0          # score uses D/E only...
    assert any("FCF yield excluded from score" in f for f in res["flags"])   # ...but it says so
    assert res["data_coverage"] < 1.0
    # a no-dividend company: payout ratio is "not applicable", not missing
    co, peers = _energy_group(payout_ratio=None, dps_ttm=0, dividend_yield=0.0)
    res = analysis.analyze(co, peers, CFG)
    assert res["params"]["dividend"]["coverage"] == 1.0
    assert not any("Payout ratio excluded" in f for f in res["flags"])


def test_fix2_low_coverage_marks_call_low_confidence():
    gone = dict(pe_trailing=None, pe_forward=None, pb=None, ev_ebitda=None, net_margin=None,
                operating_margin=None, roe=None, debt_to_equity=None, fcf_yield=None)
    co, peers = _energy_group(**gone)
    res = analysis.analyze(co, peers, CFG)
    assert res["low_confidence"] and res["data_coverage"] < 0.70
    assert res["flags"][0].startswith("Low data coverage")
    assert "LOW CONFIDENCE" in report.console_summary(res, "x")


def _fake_yf_for_fx(fin_ccy, px_ccy):
    import types

    class FakeTicker:
        def __init__(self, sym):
            self.sym = sym
            self.info = {"currentPrice": 50.0, "marketCap": 10e9, "trailingPE": 10.0, "forwardPE": 9.0,
                         "priceToBook": 1.5, "freeCashflow": 1e9, "debtToEquity": 40.0,
                         "industry": "Oil & Gas Integrated", "sector": "Energy",
                         "currency": px_ccy, "financialCurrency": fin_ccy}
            self.income_stmt = None
            self.dividends = pd.Series(dtype=float, index=pd.DatetimeIndex([]))

        def history(self, period="5y", auto_adjust=True):
            idx = pd.bdate_range("2021-01-01", periods=1300)
            return pd.DataFrame({"Close": 100 * np.cumprod(np.full(len(idx), 1.0003))}, index=idx)

    fake = types.ModuleType("yfinance")
    fake.Ticker = FakeTicker
    return fake


def _snapshot_with(fx_rate, fin_ccy="USD", px_ccy="CAD"):
    sys.modules["yfinance"] = _fake_yf_for_fx(fin_ccy, px_ccy)
    try:
        from tool import data
        data._benchmark_cache.clear()
        real = data.get_fx_rate
        data.get_fx_rate = lambda a, b: fx_rate
        try:
            return data.fetch_snapshot("SU.TO", CFG)
        finally:
            data.get_fx_rate = real
    finally:
        del sys.modules["yfinance"]


def test_fix3_fcf_converted_to_market_cap_currency():
    s = _snapshot_with(1.40)                             # USD 1bn FCF, CAD 10bn market cap
    assert abs(s["fcf_yield"] - 0.14) < 1e-9             # 1bn x 1.40 / 10bn = 14%, not 10%
    assert s["fx_used"] == {"pair": "USDCAD", "rate": 1.40}
    s = _snapshot_with(None)                             # no FX rate: leave it out, never score the raw ratio
    assert s["fcf_yield"] is None
    assert any("FCF yield excluded: no FX rate USD->CAD" in n for n in s["notes"])


def test_fix4_empty_tmx_record_is_not_verification():
    from tool import crosscheck
    snap = {"price": 150.0, "market_cap": 2.1e11, "pe_trailing": 14.0, "pb": 2.0, "dividend_yield": 0.04, "roe": 0.15}
    empty = {k: None for k in crosscheck.TOLERANCE}
    notes = crosscheck.apply_one(dict(snap), empty)
    assert len(notes) == 1 and "nothing was verified" in notes[0]
    nan_view = dict(empty, price=float("nan"))
    assert "nothing was verified" in crosscheck.apply_one(dict(snap), nan_view)[0]
    partial = dict(empty, price=150.5, pb=2.05)
    notes = crosscheck.apply_one(dict(snap), partial)
    assert any("2/6 compared" in n and "within tolerance" in n for n in notes)


def test_fix5_peers_without_common_months_do_not_crash():
    def hist(start, n, step=1.0):
        return {str(p): 100.0 * step ** i for i, p in enumerate(pd.period_range(start, periods=n, freq="M"))}
    co, peers = _energy_group()
    co["monthly_prices"] = {**hist("2021-01", 48, 1.01), "2022-06": 70.0}
    peers[0]["monthly_prices"] = hist("2018-01", 24)     # 2018-2019 only
    peers[1]["monthly_prices"] = hist("2021-01", 24)     # 2021-2022 only: no overlap with the first peer
    res = analysis.analyze(co, peers, CFG)               # used to raise IndexError
    assert res["drawdown_context"]["sector_error"]
    assert any("Sector drawdown comparison unavailable" in f for f in res["flags"])
    assert "Sector index not available" in report.html_report(res, "x", "note", 1)   # report still builds


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok ", name)
    res, text = test_full_bank_run()
    print(report.console_summary(res, text))

