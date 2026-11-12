"""Test client: connects to the running MCP server over SSE and calls every tool once.

    python server.py                      # terminal 1
    python test_client.py                 # terminal 2   (or: python test_client.py --url http://host:8001/sse)

Exit code 0 = all three tools answered over SSE with the expected response shapes.
(This client is also the pattern the LangGraph worker uses: it is the MCP *client*; the server is the MCP *host*.)
"""
import argparse
import asyncio
import json
import os
import sys

from mcp import ClientSession
from mcp.client.sse import sse_client


def payload(result) -> dict:
    if getattr(result, "structuredContent", None):
        return result.structuredContent
    return json.loads(result.content[0].text)


def expect(cond: bool, label: str, data) -> None:
    print(f"[{'ok' if cond else 'FAIL'}] {label}: {json.dumps(data, ensure_ascii=False)[:300]}")
    if not cond:
        sys.exit(1)


async def main(url: str) -> None:
    async with sse_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {t.name for t in (await session.list_tools()).tools}
            expect(tools == {"resolve_brand", "lookup_drug", "check_interaction"}, "tools listed", sorted(tools))

            r = payload(await session.call_tool("resolve_brand", {"brand": "Napa 500"}))
            expect(r.get("status") in {"resolved", "unresolved"}, "resolve_brand('Napa 500')", r)
            if r["status"] == "resolved":
                expect({"generic", "confidence", "verified", "source", "match_type"} <= r.keys(),
                       "resolved result carries confidence AND its basis", r)

            r = payload(await session.call_tool("resolve_brand", {"brand": "Zzqxyw"}))
            expect(r.get("status") == "unresolved", "unknown brand is unresolved, not guessed", r)

            r = payload(await session.call_tool("lookup_drug", {"generic_name": "warfarin"}))
            expect(r.get("status") in {"found", "not_found"}, "lookup_drug('warfarin')", r)

            r = payload(await session.call_tool("check_interaction", {"drug_a": "warfarin", "drug_b": "aspirin"}))
            expect(r.get("status") in {"found", "no_record"}, "check_interaction('warfarin','aspirin')", r)
            if r["status"] == "no_record":
                expect("not mean the combination is safe" in r["note"], "no_record never claims safe", r)
    print("all tools answered over SSE")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get("MCP_SERVER_URL", "http://localhost:8001/sse"))
    asyncio.run(main(ap.parse_args().url))
