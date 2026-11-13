"""The finance maths. No LLM here: plain functions that take numbers and return numbers."""
from math import comb, exp, log, sqrt
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import brentq, minimize
from scipy.stats import norm

# Daily closing prices of 15 US stocks, 2016-01-04 to 2026-11-06 (one column per ticker)
PRICES = pd.read_csv(Path(__file__).parent / "data" / "prices.csv", index_col="date", parse_dates=True)
TICKERS = list(PRICES.columns)
LAST_DATE = PRICES.index[-1].date().isoformat()
RISK_FREE = 0.042   # 3-month US Treasury bill yield, Nov 2026 (FRED series DGS3MO = 4.21%)
YEAR = 252          # trading days per year


def check_tickers(tickers):
    unknown = [t for t in tickers if t not in TICKERS]
    if unknown:
        raise ValueError(f"Ticker(s) {unknown} are not in the dataset. Available: {TICKERS}")


# 1. Statistics of one stock -------------------------------------------------------------
def stock_stats(ticker, days=YEAR):
    check_tickers([ticker])
    prices = PRICES[ticker].iloc[-(days + 1):]
    log_returns = np.log(prices).diff().dropna()
    return {
        "ticker": ticker,
        "date": LAST_DATE,
        "last_price": prices.iloc[-1],
        "return_over_period": prices.iloc[-1] / prices.iloc[0] - 1,
        "annual_volatility": log_returns.std() * sqrt(YEAR),
        "max_drawdown": (prices / prices.cummax() - 1).min(),
        "period_days": days,
    }


# 2. Options: Black-Scholes and implied volatility ----------------------------------------
def black_scholes(S, K, T, r, sigma, option_type="call"):
    """European option price, delta and vega (vega = price change for +1% volatility)."""
    d1 = (log(S / K) + (r + sigma ** 2 / 2) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    if option_type == "call":
        price = S * norm.cdf(d1) - K * exp(-r * T) * norm.cdf(d2)
        delta = norm.cdf(d1)
    else:
        price = K * exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
        delta = norm.cdf(d1) - 1
    vega = S * norm.pdf(d1) * sqrt(T) / 100
    return price, delta, vega


def implied_volatility(price, S, K, T, r, option_type="call"):
    """The volatility that makes Black-Scholes equal the market price."""
    # No-arbitrage range: a call is worth at least S - K*e^(-rT) and at most S (similarly for a put)
    if option_type == "call":
        low, high = max(S - K * exp(-r * T), 0), S
    else:
        low, high = max(K * exp(-r * T) - S, 0), K * exp(-r * T)
    if not low < price < high:
        raise ValueError(f"Price {price} is outside the no-arbitrage range ({low:.2f}, {high:.2f}), "
                         f"so no implied volatility exists.")
    return brentq(lambda sigma: black_scholes(S, K, T, r, sigma, option_type)[0] - price, 1e-4, 5)


# 3. Portfolio risk: Value-at-Risk and Expected Shortfall ---------------------------------
def portfolio_risk(tickers, weights, value=1_000_000, confidence=0.99, days=750):
    """Historical 1-day VaR and ES: what the portfolio would have lost on its worst days."""
    check_tickers(tickers)
    w = np.array(weights, dtype=float)
    w = w / w.sum()                                    # weights always add up to 100%
    returns = PRICES[tickers].pct_change().dropna().iloc[-days:]
    losses = -(returns.values @ w) * value             # daily loss in dollars
    var = np.quantile(losses, confidence)              # loss exceeded only (1 - confidence) of the days
    es = losses[losses >= var].mean()                  # average loss on those worst days
    cov = returns.cov().values
    contribution = w * (cov @ w) / (w @ cov @ w)       # each stock's share of portfolio variance
    return {
        "value": value,
        "confidence": confidence,
        "VaR_1day": var,
        "ES_1day": es,
        "risk_contribution": dict(zip(tickers, contribution)),
        "weights": dict(zip(tickers, w)),
        "history_days": days,
        "date": LAST_DATE,
    }


# 4. Portfolio optimisation: lowest volatility using at most k stocks ----------------------
def min_variance_weights(cov, max_weight):
    """Long-only weights with the lowest variance for a given set of stocks."""
    n = len(cov)
    result = minimize(lambda w: w @ cov @ w, np.ones(n) / n, method="SLSQP",
                      bounds=[(0, max_weight)] * n,
                      constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1}])
    return result.x


def optimize_portfolio(max_stocks=4, max_weight=0.4, days=756, iterations=500, seed=0):
    """Simulated annealing over groups of `max_stocks` stocks (there are C(15, k) possible groups)."""
    if max_stocks * max_weight < 1:
        raise ValueError(f"Impossible: {max_stocks} stocks x {max_weight:.0%} max each is less than 100%.")
    returns = PRICES.pct_change().dropna().iloc[-days:]
    cov = returns.cov().values * YEAR
    mean = returns.mean().values * YEAR
    rng = np.random.default_rng(seed)
    cache = {}

    def volatility(group):                             # objective: volatility of the best weights for this group
        if group not in cache:
            idx = list(group)
            w = min_variance_weights(cov[np.ix_(idx, idx)], max_weight)
            cache[group] = (sqrt(w @ cov[np.ix_(idx, idx)] @ w), w)
        return cache[group][0]

    def neighbour(group):                              # swap one stock in the group for one outside it
        inside = list(group)
        outside = [i for i in range(len(TICKERS)) if i not in group]
        inside[rng.integers(max_stocks)] = rng.choice(outside)
        return tuple(sorted(inside))

    current = tuple(sorted(rng.choice(len(TICKERS), max_stocks, replace=False)))
    best = current
    temperature = 0.05                                 # accepts a 5% worse group with probability e^-1 at the start
    for _ in range(iterations):
        candidate = neighbour(current)
        change = (volatility(candidate) - volatility(current)) / volatility(current)
        if change < 0 or rng.random() < exp(-change / temperature):
            current = candidate
        if volatility(current) < volatility(best):
            best = current
        temperature *= 0.99                            # geometric cooling

    idx = list(best)
    w = cache[best][1]
    return {
        "weights": {TICKERS[i]: wi for i, wi in zip(idx, w) if wi > 0.001},
        "annual_volatility": volatility(best),
        "expected_annual_return": mean[idx] @ w,
        "groups_evaluated": len(cache),
        "groups_possible": comb(len(TICKERS), max_stocks),
        "history_days": days,
        "date": LAST_DATE,
    }
