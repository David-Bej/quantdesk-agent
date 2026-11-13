# QuantDesk Agent

An LLM agent that answers trading-desk questions such as *"What's the 1-day VaR of my portfolio?"* or *"Price a 3-month call on AAPL"*. **The LLM decides which tool to use, and the tools do the maths.** The model is never allowed to calculate a number itself.

Final project for **SI3003 Inteligencia Artificial** (EAFIT, 2026-2), **Option B: agent with tools**.

## 1. Author

- David Bejman Lehrer

## 2. Problem

An analyst on a trading or risk desk needs quick answers: what an option is worth, how much a portfolio could lose in a day, which stocks give the calmest portfolio. A chat model alone is not reliable for this, because it can't compute Black-Scholes or a quantile and will make up plausible-looking numbers. Real finance code is reliable, but it isn't conversational.

**The solution:** the LLM understands the question and picks a tool. The tool computes the answer on real price data, and the LLM explains the result.

**Out of scope:** live prices (the data ends 2026-11-06), stocks outside the 15 in the dataset, and investment advice.

## 3. Why Option B (agent) and not Option A (RAG)

The answers are calculations on data, not text that sits in a document, so there is nothing for RAG to retrieve. What's needed is a model that can call functions, which is what an agent does.

## 4. How it works

```
question → LLM → picks a tool + arguments → we run the tool → result goes back to the LLM → ... → answer
```

| Tool | What it does | Method |
|---|---|---|
| `get_stock_stats` | last price, 1-year return, volatility, max drawdown | statistics of daily returns |
| `price_option` | option price, delta, vega | Black-Scholes |
| `get_implied_volatility` | volatility implied by an option's market price | Black-Scholes solved backwards (Brent); rejects prices that break no-arbitrage bounds |
| `get_portfolio_risk` | 1-day Value-at-Risk, Expected Shortfall, each stock's share of the risk | historical simulation over the last 750 days |
| `optimize_portfolio` | lowest-volatility portfolio with at most *k* stocks | **simulated annealing** (from Part 1 of the course) to choose the stocks, SLSQP to choose the weights |

**The loop** (`agent.py`, about 60 lines) follows the Lecture 11 notebook:
1. Send the question and the tool descriptions to the LLM.
2. If the LLM asks for tools, run them and send back the results.
3. Repeat until the LLM answers without asking for a tool.

**Limits.** At most **6 tool calls** per question. Once the limit is reached, further calls are not run: the LLM gets the message *"Tool limit reached. Answer now with the results you already have."* As a safety net, the loop also stops after **8 rounds** with the LLM.

**Errors.** If a tool fails (unknown ticker, impossible option price), the error text goes back to the LLM so it can explain it instead of inventing a result.

## 5. How to run

**Google Colab:** open `QuantDesk.ipynb`. Add your NVIDIA key as a Colab secret named `NVIDIA_API_KEY` (free at [build.nvidia.com](https://build.nvidia.com)), then choose *Run all*.

**Locally:**
```bash
pip install -r requirements.txt
python -m pytest -q                  # 7 tests of the maths
export NVIDIA_API_KEY=nvapi-...
python run_test_cases.py             # runs the 5 test cases -> results/test_cases.md
```

## 6. Data and tools used

- **Prices:** `data/prices.csv`, daily closing prices (adjusted for splits) of AAPL, ACN, ADBE, CRM, GOOG, INTU, LRCX, META, MSFT, NFLX, NVDA, RMD, SAP, TSLA and TSM, from 2016-01-04 to 2026-11-06. Source: the [Pubmarks datasets](https://github.com/Pubmarks/datasets) repository on GitHub.
- **Risk-free rate:** 4.2%, the 3-month US T-bill yield in November 2026 (FRED series DGS3MO).
- **LLM:** `nvidia/nemotron-3.5-super-vl-120b-a12b` on NVIDIA NIM, the model used in the course's Lecture 11 notebooks, called through the `openai` Python client.
- **Libraries:** numpy, pandas, scipy, openai, pytest.

## 7. The five test cases

Expected values come from running the tools directly, without the LLM. The full output of each run (tool, arguments, result, answer) is in **`results/test_cases.md`**.

| # | Question | Expected tool(s) | Expected result | Assessment |
|---|---|---|---|---|
| C1 | 3-month at-the-money call on AAPL, with delta and vega | `price_option(AAPL, call, months=3)` | price **\$18.73**, delta 0.558, vega \$0.676 per 1% vol (spot \$342.37, vol 24.9%) | Correct: used price_option with months=3; price \$18.73, delta and vega match. |
| C2 | 1-day 99% VaR and ES of \$1M in 40% NVDA, 30% MSFT, 30% RMD | `get_portfolio_risk` | VaR **\$43,681**, ES **\$52,801**. NVDA carries 63% of the risk | Correct: one get_portfolio_risk call; VaR \$43,681 and ES \$52,801 match; identified NVDA. |
| C3 | Was NVDA or MSFT more volatile last year, and what did each return? | `get_stock_stats` twice | NVDA vol 38.5%, return −4.4%. MSFT vol 33.4%, return +4.6% | Correct: two get_stock_stats calls; NVDA more volatile (38.5% vs 33.4%). |
| C4 | Lowest-volatility portfolio with at most 4 stocks, then its VaR on \$1M | `optimize_portfolio`, then `get_portfolio_risk` with the weights it returned | MSFT 31.5%, AAPL 29.4%, RMD 25.1%, NFLX 14.1%; vol 19.1%; VaR **\$30,692** | Correct: optimize_portfolio, then get_portfolio_risk with the returned weights; VaR \$30,692 matches. |
| C5 | **Edge case:** an AAPL 300-strike call expiring in 30 days costs \$20. What's its implied volatility? | `get_implied_volatility` returns an error | **No implied volatility exists.** \$20 is below the \$43.40 minimum a no-arbitrage price allows, so the agent must say so and not invent a number | Correct: tool returned the no-arbitrage error; agent explained no IV exists and invented no number. |

C3 needs two calls to the same tool. C4 is the hardest case: the LLM has to copy the output of one tool into the input of the next.

## 8. Analysis: errors, limitations, improvements

**Errors observed while building it**
- **Retired model.** The first run failed with `410 Gone`: NVIDIA had retired the original model, `meta/llama-3.3-70b-instruct`, on 2026-08-26. I switched to the course's Nemotron model. Any project that depends on a hosted LLM can break this way.
- **Unit conversion by the LLM.** In an early run the model turned "3 months" into 90 days. That is 0.2466 years instead of 0.25, so the price came out at \$18.59 instead of \$18.73. **Fix:** the tools now accept `months` or `days` directly, so the model never converts units.
- **Misread units.** The tool returned a vega of 0.671, already per 1% of volatility, and the model divided it by 100 again. **Fix:** the result field is now called `vega_per_1pct_vol`, and the system prompt says to report it as given.
- Final run: all five cases behaved as expected.

**Limitations**
- The data is a fixed snapshot, not live prices, and covers only 15 large US stocks (mostly tech).
- Black-Scholes assumes constant volatility. Historical VaR assumes the next day looks like the last 750.
- In C4 the model copies weights by hand from one tool to the next, which is a possible source of mistakes.

**Possible improvements:** live market data; letting `get_portfolio_risk` read the optimised portfolio directly instead of having the LLM copy the weights; more tools, such as a GARCH volatility forecast.

## 9. Files

```
quant.py           the finance maths (no LLM)
tools.py           the 5 tools + their descriptions for the LLM
agent.py           the agent loop
run_test_cases.py  the 5 test cases -> results/test_cases.md
test_quant.py      7 tests of the maths
QuantDesk.ipynb    Colab notebook that runs everything
data/prices.csv    price data
```

*Use of generative AI: this project was developed with help from Claude (Anthropic) for code and documentation, in line with the course policy.*
