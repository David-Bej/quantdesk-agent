"""The agent loop: the LLM picks a tool, we run it, we send back the result, until the LLM answers."""
import json
import os

from openai import OpenAI

import quant
from tools import TOOLS, run_tool

MODEL = "nvidia/nemotron-3.5-super-vl-120b-a12b"   # the model used in the course (Lecture 11)
MAX_TOOL_CALLS = 6                                  # tool runs allowed per question
MAX_ROUNDS = 8                                      # LLM calls allowed per question (stops endless loops)

SYSTEM_PROMPT = f"""You are QuantDesk, an assistant for a trading desk.
You answer with tools that compute on daily prices of {', '.join(quant.TICKERS)} up to {quant.LAST_DATE}.
Rules:
- Every number in your answer must come from a tool result. Never calculate or guess numbers yourself.
- Give maturities in the unit the user used (months or days). Give weights and volatilities as decimals.
- Vega is already per 1% of volatility: report it as given.
- If a tool returns an error, explain it simply. Do not make up a result.
- State the main assumptions (date of the data, volatility used, risk-free rate {quant.RISK_FREE}).
- Answer in the user's language, briefly. You do not give investment advice."""

if not os.environ.get("NVIDIA_API_KEY"):
    raise SystemExit("Set NVIDIA_API_KEY first (in Colab: the Secrets panel on the left).")
client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=os.environ["NVIDIA_API_KEY"])


def ask(question, max_tool_calls=MAX_TOOL_CALLS, verbose=True):
    """Answer one question. Returns the final answer and the list of tool calls made."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": question}]
    calls = []
    if verbose:
        print(f"\nQUESTION: {question}")

    for _ in range(MAX_ROUNDS):
        response = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS,
                                                  temperature=0.2, max_tokens=4096)
        message = response.choices[0].message

        if not message.tool_calls:                         # no tool requested: this is the answer
            if verbose:
                print(f"ANSWER: {message.content}")
            return message.content, calls

        messages.append({"role": "assistant", "content": message.content or "", "tool_calls": [
            {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}}
            for c in message.tool_calls]})

        for call in message.tool_calls:
            if len(calls) < max_tool_calls:
                result = run_tool(call.function.name, call.function.arguments)
            else:                                          # limit reached: refuse and ask for an answer
                result = json.dumps({"error": f"Tool limit of {max_tool_calls} calls reached. "
                                              "Answer now with the results you already have."})
            calls.append({"tool": call.function.name, "arguments": call.function.arguments, "result": result})
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
            if verbose:
                print(f"  TOOL: {call.function.name}({call.function.arguments})\n  RESULT: {result[:300]}")

    return "Stopped: the model kept asking for tools after the limit.", calls
