"""Checks that the maths is right. Run with: python -m pytest -q"""
import itertools
import json

import numpy as np
import pytest

import quant
from tools import run_tool


def test_black_scholes_textbook_example():
    # Hull, Options, Futures & Other Derivatives: S=42, K=40, r=10%, sigma=20%, T=0.5 -> call 4.76, put 0.81
    assert quant.black_scholes(42, 40, 0.5, 0.10, 0.20, "call")[0] == pytest.approx(4.76, abs=0.005)
    assert quant.black_scholes(42, 40, 0.5, 0.10, 0.20, "put")[0] == pytest.approx(0.81, abs=0.005)


def test_put_call_parity():
    call = quant.black_scholes(100, 95, 0.75, 0.04, 0.3, "call")[0]
    put = quant.black_scholes(100, 95, 0.75, 0.04, 0.3, "put")[0]
    assert call - put == pytest.approx(100 - 95 * np.exp(-0.04 * 0.75))


def test_implied_volatility_recovers_the_input():
    price = quant.black_scholes(100, 110, 0.5, 0.04, 0.35, "call")[0]
    assert quant.implied_volatility(price, 100, 110, 0.5, 0.04, "call") == pytest.approx(0.35)


def test_implied_volatility_rejects_impossible_price():
    with pytest.raises(ValueError, match="no-arbitrage"):
        quant.implied_volatility(20, 342.37, 300, 30 / 365, 0.042, "call")   # worth at least ~43.40


def test_var_and_es():
    risk = quant.portfolio_risk(["NVDA", "MSFT", "RMD"], [0.4, 0.3, 0.3])
    assert 0 < risk["VaR_1day"] < risk["ES_1day"]
    assert sum(risk["risk_contribution"].values()) == pytest.approx(1)


def test_simulated_annealing_finds_the_best_group():
    returns = quant.PRICES.pct_change().dropna().iloc[-756:]
    cov = returns.cov().values * quant.YEAR

    def vol(group):
        sub = cov[np.ix_(group, group)]
        w = quant.min_variance_weights(sub, 0.4)
        return w @ sub @ w

    best = min(itertools.combinations(range(len(quant.TICKERS)), 4), key=vol)   # try all 1,365 groups
    result = quant.optimize_portfolio(max_stocks=4, max_weight=0.4)
    assert set(result["weights"]) == {quant.TICKERS[i] for i in best}


def test_tool_errors_are_returned_not_raised():
    result = json.loads(run_tool("get_stock_stats", '{"ticker": "AMZN"}'))
    assert "not in the dataset" in result["error"]
