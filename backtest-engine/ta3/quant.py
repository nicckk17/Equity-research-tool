"""Quant toolkit: option pricing, Monte Carlo, sizing, volatility/regime models, risk metrics.
(First draft by the local qwen3-coder model; reviewed and corrected by Claude: drawdown signs, Sharpe
annualisation, look-ahead in vol targeting, block bootstrap, GARCH output as volatility not variance.)"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import brentq, minimize
from scipy.stats import norm


# ---------------------------------------------------------------- Black-Scholes-Merton
def _d12(S, K, T, r, sigma, q):
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    return d1, d1 - sigma * np.sqrt(T)


def bs_price(S, K, T, r, sigma, kind="call", q=0.0):
    """European option price (continuous dividend yield q); intrinsic value at expiry."""
    if T <= 0 or sigma <= 0:
        return max(S - K, 0.0) if kind == "call" else max(K - S, 0.0)
    d1, d2 = _d12(S, K, T, r, sigma, q)
    if kind == "call":
        return S * np.exp(-q * T) * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    return K * np.exp(-r * T) * norm.cdf(-d2) - S * np.exp(-q * T) * norm.cdf(-d1)


def bs_greeks(S, K, T, r, sigma, kind="call", q=0.0):
    """delta, gamma, vega (per 1.00 vol), theta (per year), rho (per 1.00 rate)."""
    if T <= 0 or sigma <= 0:
        itm = (S > K) if kind == "call" else (S < K)
        return dict(delta=(1.0 if kind == "call" else -1.0) * float(itm), gamma=0.0, vega=0.0, theta=0.0, rho=0.0)
    d1, d2 = _d12(S, K, T, r, sigma, q); eq, er = np.exp(-q * T), np.exp(-r * T)
    gamma = eq * norm.pdf(d1) / (S * sigma * np.sqrt(T)); vega = S * eq * norm.pdf(d1) * np.sqrt(T)
    decay = -S * eq * norm.pdf(d1) * sigma / (2 * np.sqrt(T))
    if kind == "call":
        return dict(delta=eq * norm.cdf(d1), gamma=gamma, vega=vega,
                    theta=decay - r * K * er * norm.cdf(d2) + q * S * eq * norm.cdf(d1), rho=K * T * er * norm.cdf(d2))
    return dict(delta=eq * (norm.cdf(d1) - 1), gamma=gamma, vega=vega,
                theta=decay + r * K * er * norm.cdf(-d2) - q * S * eq * norm.cdf(-d1), rho=-K * T * er * norm.cdf(-d2))


def implied_vol(price, S, K, T, r, kind="call", q=0.0):
    """Implied volatility by Brent's method on [1e-4, 5]; NaN if the price is outside no-arbitrage bounds."""
    try:
        return brentq(lambda s: bs_price(S, K, T, r, s, kind, q) - price, 1e-4, 5.0)
    except ValueError:
        return float("nan")


# ---------------------------------------------------------------- Monte Carlo
def _dd(eq):
    return (eq / np.maximum.accumulate(eq, axis=-1) - 1).min(axis=-1)


def mc_trade_paths(r_per_trade, n_trades=None, n_sims=5000, risk=0.01, seed=1):
    """Resample trades (R units) with replacement; equity x (1 + risk*R) per trade. Drawdowns are negative."""
    r = np.asarray(r_per_trade, float); r = r[np.isfinite(r)]; n = n_trades or len(r)
    rng = np.random.default_rng(seed)
    eq = np.cumprod(1 + risk * rng.choice(r, size=(n_sims, n), replace=True), axis=1)
    eq = np.concatenate([np.ones((n_sims, 1)), eq], axis=1)
    dd = _dd(eq); fin = eq[:, -1]
    return dict(final=fin, max_dd=dd, dd_p50=float(np.percentile(dd, 50)), dd_p95=float(np.percentile(dd, 5)),
                final_p5=float(np.percentile(fin, 5)), final_p50=float(np.percentile(fin, 50)),
                final_p95=float(np.percentile(fin, 95)), prob_loss=float((fin < 1).mean()))


def risk_of_ruin(r_per_trade, risk=0.01, ruin=0.5, n_trades=1000, n_sims=5000, seed=1):
    """Share of simulated paths whose equity ever falls to (1 - ruin) or below."""
    r = np.asarray(r_per_trade, float); r = r[np.isfinite(r)]
    eq = np.cumprod(1 + risk * np.random.default_rng(seed).choice(r, size=(n_sims, n_trades)), axis=1)
    return float((eq.min(axis=1) <= 1 - ruin).mean())


def block_bootstrap_paths(returns, n_paths=1000, block=20, horizon=None, seed=1):
    """Simulated return paths built from random overlapping blocks of the history (keeps streaks/clusters)."""
    x = np.asarray(returns, float); n = len(x); h = horizon or n; block = min(block, n)
    rng = np.random.default_rng(seed); nb = int(np.ceil(h / block))
    starts = rng.integers(0, n - block + 1, size=(n_paths, nb))
    idx = (starts[:, :, None] + np.arange(block)).reshape(n_paths, -1)[:, :h]
    return x[idx]


def gbm_paths(S0, mu, sigma, days, n_paths=1000, seed=1, dt=1 / 252):
    """Geometric Brownian motion price paths, shape (n_paths, days + 1)."""
    z = np.random.default_rng(seed).standard_normal((n_paths, days))
    steps = np.exp((mu - 0.5 * sigma ** 2) * dt + sigma * np.sqrt(dt) * z)
    return S0 * np.concatenate([np.ones((n_paths, 1)), np.cumprod(steps, axis=1)], axis=1)


# ---------------------------------------------------------------- sizing
def kelly_fraction(r_per_trade):
    """Continuous Kelly fraction of equity to risk per 1R (mean/variance); 0 if no edge. Use 1/4-1/2 of it."""
    r = np.asarray(r_per_trade, float); r = r[np.isfinite(r)]
    m, v = r.mean(), r.var()
    return float(m / v) if m > 0 and v > 0 else 0.0


def position_size(equity, entry, stop, risk_frac=0.01, max_notional_frac=0.2):
    """Shares so a stop-out loses risk_frac of equity, capped at max_notional_frac of equity."""
    if entry == stop or entry <= 0:
        return 0
    return int(min(np.floor(equity * risk_frac / abs(entry - stop)), np.floor(equity * max_notional_frac / entry)))


def vol_target_weight(returns, target_vol=0.10, lookback=20, cap=1.0, periods=252):
    """Exposure that targets target_vol, using only past returns (shifted 1 bar); NaN until enough history."""
    r = pd.Series(returns)
    vol = r.rolling(lookback).std() * np.sqrt(periods)
    return (target_vol / vol).clip(upper=cap).shift(1)


# ---------------------------------------------------------------- regime / volatility
def hurst(prices, max_lag=100):
    """Hurst exponent from the scaling of log-price differences: <0.5 mean-reverting, >0.5 trending."""
    x = np.log(np.asarray(prices, float)); lags = np.arange(2, min(max_lag, len(x) // 4) + 1)
    sd = np.array([np.std(x[l:] - x[:-l]) for l in lags])
    return float(np.polyfit(np.log(lags), np.log(sd), 1)[0])


def garch11(returns):
    """GARCH(1,1) by maximum likelihood. Returns omega, alpha, beta, cond_vol (std dev per period)."""
    r = np.asarray(returns, float); r = r[np.isfinite(r)]; r = r - r.mean(); n = len(r); v0 = r.var()

    def var_path(p):
        om, a, b = p; h = np.empty(n); h[0] = v0
        for i in range(1, n):
            h[i] = om + a * r[i - 1] ** 2 + b * h[i - 1]
        return h

    def nll(p):
        if p[1] + p[2] >= 0.999:
            return 1e12
        h = var_path(p)
        return 0.5 * np.sum(np.log(h) + r ** 2 / h)

    res = minimize(nll, [v0 * 0.05, 0.05, 0.9], method="L-BFGS-B", bounds=[(1e-12, None), (0, 1), (0, 1)])
    om, a, b = res.x
    return dict(omega=float(om), alpha=float(a), beta=float(b), cond_vol=np.sqrt(var_path(res.x)),
                persistence=float(a + b), long_run_vol=float(np.sqrt(om / max(1e-12, 1 - a - b))))


# ---------------------------------------------------------------- metrics
def sharpe(returns, periods=252, rf=0.0):
    """Annualised Sharpe of per-period returns (rf per period)."""
    r = np.asarray(returns, float) - rf; s = r.std(ddof=1)
    return float(r.mean() / s * np.sqrt(periods)) if s > 0 else float("nan")


def sortino(returns, periods=252):
    """Annualised Sortino: mean over downside deviation (root mean square of negative returns)."""
    r = np.asarray(returns, float); dn = np.sqrt(np.mean(np.minimum(r, 0) ** 2))
    return float(r.mean() / dn * np.sqrt(periods)) if dn > 0 else float("nan")


def max_drawdown(equity):
    """Worst peak-to-trough fall as a negative fraction."""
    e = np.asarray(equity, float)
    return float((e / np.maximum.accumulate(e) - 1).min())


def cagr(equity, periods=252):
    """Compound annual growth rate from an equity curve sampled every period."""
    e = np.asarray(equity, float)
    return float((e[-1] / e[0]) ** (periods / max(1, len(e) - 1)) - 1)


def corr_matrix(returns_by_system):
    """Correlation of daily returns between systems (missing days = flat)."""
    return pd.DataFrame(returns_by_system).fillna(0.0).corr()
