"""MCP client used by the LangGraph agents (the LangGraph worker is the MCP *host*; this module is the *client*).

The three deterministic tools live in mcp-server/server.py and are backed by apps/drugs/services.py:

    resolve_brand(brand, strength?)   lookup_drug(generic_name)   check_interaction(drug_a, drug_b)

`call_tools([...])` opens ONE SSE session, calls every tool in order, and returns the answers plus the transport
that was really used. Honesty rule: if the MCP server is unreachable the same deterministic functions are called
directly (unless AI_TOOL_TRANSPORT=mcp_only) and `ToolBatch.transport == "direct"` + `note` say so; agents copy
that into the AgentTrace, so a trace never claims MCP when MCP was not used.

It is synchronous on purpose: it runs inside a Celery worker, never inside a request/response cycle.
"""
import asyncio
import concurrent.futures
import json
import logging
from dataclasses import dataclass

from .config import setting

logger = logging.getLogger(__name__)

TOOLS = ("resolve_brand", "lookup_drug", "check_interaction")


class ToolCallError(RuntimeError):
    """A tool could not be called or returned something unusable."""


@dataclass
class ToolBatch:
    results: list  # one dict per call, same order as the calls
    transport: str  # mcp_sse | direct | none
    note: str = ""  # why `direct` was used, when it was


def _payload(result, tool: str) -> dict:
    if getattr(result, "isError", False):
        raise ToolCallError(f"MCP tool {tool} returned an error")
    data = getattr(result, "structuredContent", None)
    if not data:
        text = next((c.text for c in (getattr(result, "content", None) or []) if getattr(c, "type", "") == "text"), None)
        if text is None:
            raise ToolCallError(f"MCP tool {tool} returned no content")
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise ToolCallError(f"MCP tool {tool} returned non-JSON content") from exc
    if isinstance(data, dict) and set(data) == {"result"} and isinstance(data["result"], dict):
        data = data["result"]  # some SDK versions wrap a dict return value
    if not isinstance(data, dict):
        raise ToolCallError(f"MCP tool {tool} returned an unexpected shape")
    return data


async def _call_over_sse(url: str, calls: list, total_timeout: float) -> list:
    from mcp import ClientSession  # imported here: the AI package may be absent in light environments
    from mcp.client.sse import sse_client

    async def _go() -> list:
        out = []
        async with sse_client(url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                for name, args in calls:
                    out.append(_payload(await session.call_tool(name, args), name))
        return out

    return await asyncio.wait_for(_go(), timeout=total_timeout)


def _run_sync(coro_factory):
    """Run a coroutine from sync code. Celery workers have no running loop; a thread covers the case where one exists."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro_factory())
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro_factory())).result()


def _direct(calls: list) -> list:
    """The exact functions the MCP server wraps. Same answers, no network hop."""
    from apps.drugs import services

    funcs = {
        "resolve_brand": services.resolve_brand,
        "lookup_drug": services.lookup_drug,
        "check_interaction": services.check_interaction,
    }
    out = []
    for name, args in calls:
        fn = funcs.get(name)
        if fn is None:
            raise ToolCallError(f"unknown tool {name!r}")
        try:
            out.append(fn(**args))
        except TypeError as exc:
            raise ToolCallError(f"bad arguments for {name}: {exc}") from exc
    return out


def call_tools(calls: list) -> ToolBatch:
    """calls: [(tool_name, {arg: value}), ...] -> ToolBatch. Raises ToolCallError when nothing can answer."""
    prepared = [(name, dict(args)) for name, args in calls]
    if not prepared:
        return ToolBatch([], "none")
    for name, _ in prepared:
        if name not in TOOLS:
            raise ToolCallError(f"unknown tool {name!r}")

    mode = str(setting("AI_TOOL_TRANSPORT", "mcp")).strip().lower()
    if mode == "direct":
        return ToolBatch(_direct(prepared), "direct", "AI_TOOL_TRANSPORT=direct")

    url = str(setting("MCP_SERVER_URL", "http://localhost:8001/sse"))
    timeout = float(setting("AI_MCP_TIMEOUT", 15.0)) + 0.2 * len(prepared)
    try:
        return ToolBatch(_run_sync(lambda: _call_over_sse(url, prepared, timeout)), "mcp_sse")
    except Exception as exc:  # noqa: BLE001 — connection errors arrive as ExceptionGroups/timeouts of many types
        if mode == "mcp_only":
            raise ToolCallError(f"MCP server failed ({exc.__class__.__name__}) and AI_TOOL_TRANSPORT=mcp_only") from exc
        logger.warning("MCP call failed (%s); using the deterministic functions directly", exc.__class__.__name__,
                       exc_info=True)
        note = f"MCP unavailable ({exc.__class__.__name__}); same deterministic functions called directly"
        return ToolBatch(_direct(prepared), "direct", note)