"""The MCP server exposes the same three tools, with the same response shapes, over the MCP protocol."""
import asyncio
import importlib.util
import json
from pathlib import Path

import pytest

pytest.importorskip("mcp")
from mcp.shared.memory import create_connected_server_and_client_session  # noqa: E402

from apps.drugs import services  # noqa: E402
from apps.drugs.models import BrandMapping, Drug  # noqa: E402

SERVER = Path(__file__).resolve().parents[2] / "mcp-server" / "server.py"


def _load_server():
    spec = importlib.util.spec_from_file_location("predictrx_mcp_server", SERVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _payload(result) -> dict:
    return result.structuredContent if getattr(result, "structuredContent", None) else json.loads(result.content[0].text)


@pytest.mark.django_db(transaction=True)
def test_tools_listed_and_callable_over_mcp():
    d = Drug.objects.create(generic_name="acetaminophen", aliases=["paracetamol"])
    Drug.objects.create(generic_name="warfarin")
    BrandMapping.objects.create(brand_name="Napa", drug=d, source="sample", confidence="0.95")
    services.invalidate_cache()
    mcp = _load_server().mcp

    async def run():
        async with create_connected_server_and_client_session(mcp._mcp_server) as session:
            names = {t.name for t in (await session.list_tools()).tools}
            resolved = _payload(await session.call_tool("resolve_brand", {"brand": "Napa 500"}))
            lookup = _payload(await session.call_tool("lookup_drug", {"generic_name": "paracetamol"}))
            pair = _payload(await session.call_tool("check_interaction", {"drug_a": "warfarin", "drug_b": "acetaminophen"}))
            return names, resolved, lookup, pair

    names, resolved, lookup, pair = asyncio.run(run())
    assert names == {"resolve_brand", "lookup_drug", "check_interaction"}
    assert resolved["status"] == "resolved" and resolved["generic"] == "acetaminophen"
    assert lookup["status"] == "found"
    assert pair["status"] == "no_record" and "not mean the combination is safe" in pair["note"]
