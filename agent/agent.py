"""Deal Hunter agent.

Spawns the MCP server as a subprocess, exposes its tools to Claude Opus 5, and
lets the model orchestrate the compare -> coupons -> cards -> best-deal pipeline
in response to a natural-language shopping request.

Usage:
    python -m agent.agent "HP Victus gaming laptop"
    python -m agent.agent            # interactive prompt

Requires:  pip install "anthropic[mcp]"  and  ANTHROPIC_API_KEY set.
"""
from __future__ import annotations

import asyncio
import os
import sys

from anthropic import AsyncAnthropic
from anthropic.lib.tools.mcp import async_mcp_tool
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

MODEL = os.getenv("DEAL_HUNTER_MODEL", "claude-opus-5")

SYSTEM = """\
You are Deal Hunter, a shopping assistant for the Indian market (prices in ₹).
Given a product, you find the cheapest real cost to buy it by comparing Amazon.in,
Flipkart, and the HP India store, then layering on the best coupon and the best
payment card.

How to work:
- For a straightforward "find me the best deal on X" request, call find_best_deal.
- When the user wants the reasoning, use the granular tools: compare_prices to
  confirm the listings are the same product, get_coupons, list_card_offers.
- Always check the same-product confidence before declaring a winner. If it's
  low, say the listings may not be identical.
- If the data source is "sample" (scrapers were blocked), say so plainly — the
  numbers are illustrative, not live.

Answer format: lead with the recommendation in one line (platform + card + coupon
+ net price). Then a short breakdown of the math (listed price - coupon - instant
discount - reward = net). Keep it concise; no filler."""


async def run(user_query: str) -> None:
    client = AsyncAnthropic()

    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.server"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )

    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as mcp_client:
            await mcp_client.initialize()
            tools = (await mcp_client.list_tools()).tools

            runner = client.beta.messages.tool_runner(
                model=MODEL,
                max_tokens=8000,
                system=SYSTEM,
                output_config={"effort": "high"},
                tools=[async_mcp_tool(t, mcp_client) for t in tools],
                messages=[{"role": "user", "content": user_query}],
            )

            async for message in runner:
                if message.stop_reason == "refusal":
                    print("[The model declined this request.]")
                    return
                for block in message.content:
                    if block.type == "text" and block.text.strip():
                        print(block.text)
                    elif block.type == "tool_use":
                        print(f"  … calling {block.name}({block.input})",
                              file=sys.stderr)


def main() -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit("Set ANTHROPIC_API_KEY (copy .env.example to .env).")

    query = " ".join(sys.argv[1:]).strip()
    if not query:
        query = input("What are you shopping for? ").strip()
    if not query:
        sys.exit("No query given.")

    asyncio.run(run(query))


if __name__ == "__main__":
    main()
