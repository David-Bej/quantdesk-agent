"""The tools the LLM can use. Each tool = a Python function + a JSON description the LLM reads."""
import json

import quant


def years(months=None, days=None):
    if months:
        return months / 12
    if days:
        return days / 365
    raise ValueError("Give the time to expiry in `months` or in `days`.")


# The tool functions ------------------------------------------------------------------------
def get_stock_stats(ticker, days=252):
    return quant.stock_stats(ticker.upper(), days)


def price_option(ticker, option_type, months=None, days=None, strike_pct_of_spot=1.0, volatility=None):
    ticker = ticker.upper()
    stats = quant.stock_stats(ticker)
    S = stats["last_price"]
    K = S * strike_pct_of_spot
    T = years(months, days)
    sigma = volatility if volatility else stats["annual_volatility"]
    price, delta, vega = quant.black_scholes(S, K, T, quant.RISK_FREE, sigma, option_type)
    return {
        "price": price, "delta": delta, "vega_per_1pct_vol": vega,
        "spot": S, "strike": K, "years_to_expiry": T, "volatility_used": sigma,
        "volatility_source": "user input" if volatility else "1-year historical volatility",
        "risk_free_rate": quant.RISK_FREE, "model": "Black-Scholes", "date": quant.LAST_DATE,
    }


def get_implied_volatility(ticker, option_type, option_price, strike, months=None, days=None):
    ticker = ticker.upper()
    S = quant.stock_stats(ticker)["last_price"]
    T = years(months, days)
    iv = quant.implied_volatility(option_price, S, strike, T, quant.RISK_FREE, option_type)
    return {"implied_volatility": iv, "spot": S, "strike": strike, "years_to_expiry": T,
            "historical_volatility": quant.stock_stats(ticker)["annual_volatility"], "date": quant.LAST_DATE}


def get_portfolio_risk(tickers, weights, value=1_000_000, confidence=0.99):
    return quant.portfolio_risk([t.upper() for t in tickers], weights, value, confidence)


def optimize_portfolio(max_stocks=4, max_weight=0.4):
    return quant.optimize_portfolio(max_stocks, max_weight)


FUNCTIONS = {f.__name__: f for f in
             [get_stock_stats, price_option, get_implied_volatility, get_portfolio_risk, optimize_portfolio]}


# The descriptions the LLM reads (OpenAI "tools" format) -------------------------------------
def tool(name, description, properties, required):
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {
        "type": "object", "properties": properties, "required": required}}}


TICKER = {"type": "string", "description": f"Stock ticker, one of: {', '.join(quant.TICKERS)}"}
OPTION_TYPE = {"type": "string", "enum": ["call", "put"]}
MONTHS = {"type": "number", "description": "Time to expiry in months, if the user gave months (e.g. 3)."}
DAYS = {"type": "number", "description": "Time to expiry in days, if the user gave days (e.g. 30)."}

TOOLS = [
    tool("get_stock_stats",
         "Last price, return, annual volatility and max drawdown of one stock over the last `days` trading days.",
         {"ticker": TICKER, "days": {"type": "integer", "description": "Trading days to look back. Default 252 (1 year)."}},
         ["ticker"]),
    tool("price_option",
         "Black-Scholes price, delta and vega of a European option on a stock. Spot = last price; "
         "volatility = 1-year historical volatility unless given.",
         {"ticker": TICKER, "option_type": OPTION_TYPE, "months": MONTHS, "days": DAYS,
          "strike_pct_of_spot": {"type": "number", "description": "Strike as a fraction of spot: 1.0 = at-the-money, 1.1 = 10% above."},
          "volatility": {"type": "number", "description": "Optional volatility as a decimal (0.25 = 25%)."}},
         ["ticker", "option_type"]),
    tool("get_implied_volatility",
         "Implied volatility of a European option from its market price. Returns an error if the price "
         "breaks the no-arbitrage bounds.",
         {"ticker": TICKER, "option_type": OPTION_TYPE, "option_price": {"type": "number"},
          "strike": {"type": "number", "description": "Strike price in dollars."}, "months": MONTHS, "days": DAYS},
         ["ticker", "option_type", "option_price", "strike"]),
    tool("get_portfolio_risk",
         "1-day Value-at-Risk and Expected Shortfall (historical, last 750 days) of a stock portfolio in "
         "dollars, plus each stock's share of the risk.",
         {"tickers": {"type": "array", "items": {"type": "string"}},
          "weights": {"type": "array", "items": {"type": "number"}, "description": "Decimals, same order as tickers (0.4 = 40%)."},
          "value": {"type": "number", "description": "Portfolio value in dollars. Default 1,000,000."},
          "confidence": {"type": "number", "description": "Default 0.99."}},
         ["tickers", "weights"]),
    tool("optimize_portfolio",
         "Lowest-volatility long-only portfolio using at most `max_stocks` of the available stocks "
         "(found with simulated annealing).",
         {"max_stocks": {"type": "integer", "description": "Default 4."},
          "max_weight": {"type": "number", "description": "Maximum weight per stock as a decimal. Default 0.4."}},
         []),
]


# Running a tool the LLM asked for ------------------------------------------------------------
def rounded(x):
    if isinstance(x, dict):
        return {k: rounded(v) for k, v in x.items()}
    if isinstance(x, float):                     # also catches numpy floats
        return round(float(x), 4)
    return x


def run_tool(name, arguments):
    """Run the tool and return its result as JSON text. Errors are returned too, so the LLM can explain them."""
    try:
        result = rounded(FUNCTIONS[name](**json.loads(arguments)))
    except Exception as error:
        result = {"error": str(error)}
    return json.dumps(result)
