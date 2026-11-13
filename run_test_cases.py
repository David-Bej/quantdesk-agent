"""The five test cases of the project. Run them with: python run_test_cases.py"""
import json
from pathlib import Path

from agent import MODEL, ask

TEST_CASES = [
    ("C1 · routine",
     "What is the fair value of a 3-month at-the-money European call on AAPL, using its 1-year "
     "historical volatility? Give me delta and vega too."),
    ("C2 · routine",
     "I hold $1,000,000 split 40% NVDA, 30% MSFT and 30% RMD. What are my 1-day 99% VaR and "
     "Expected Shortfall, and which position contributes most to the risk?"),
    ("C3 · routine",
     "Which was more volatile over the last year, NVDA or MSFT, and how much did each return?"),
    ("C4 · needs two tools in a row",
     "Build the lowest-volatility portfolio using at most 4 stocks and no more than 40% in any one. "
     "Then tell me its 1-day 99% VaR on $1,000,000."),
    ("C5 · edge case",
     "An AAPL call with strike 300 expiring in 30 days is trading at $20. What implied volatility does that price imply?"),
]


def run_all(path="results/test_cases.md"):
    lines = [f"# Test case results\n\nModel: `{MODEL}`\n"]
    for name, question in TEST_CASES:
        answer, calls = ask(question)
        lines.append(f"## {name}\n\n**Question:** {question}\n")
        for c in calls:
            lines.append(f"- **Tool:** `{c['tool']}`  \n  **Arguments:** `{c['arguments']}`  \n"
                         f"  **Result:** `{c['result']}`")
        lines.append(f"\n**Answer:** {answer}\n\n**Assessment:** _(write one line)_\n")
    Path(path).parent.mkdir(exist_ok=True)
    Path(path).write_text("\n".join(lines))
    print(f"\nSaved to {path}")


if __name__ == "__main__":
    run_all()
