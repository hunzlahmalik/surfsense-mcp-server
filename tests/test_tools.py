"""Smoke tests for every MCP tool — verify URL, query string, and auth header."""

from __future__ import annotations

import json

import httpx
import pytest
from fastmcp import Client

from surfsense_mcp.server import get_stdio_mcp
from tests.conftest import FAKE_JWT, json_response


def _assert_bearer(request: httpx.Request) -> None:
    assert request.headers.get("Authorization") == f"Bearer {FAKE_JWT}"


async def _call_tool(tool_name: str, arguments: dict) -> dict | list:
    mcp = get_stdio_mcp()
    async with Client(mcp) as client:
        result = await client.call_tool(tool_name, arguments)
    # FastMCP wraps JSON tool results in TextContent; parse back out.
    assert result.content, "tool returned no content"
    text = result.content[0].text  # type: ignore[attr-defined]
    return json.loads(text)


async def test_list_search_spaces(mock_transport) -> None:
    recorded = mock_transport(
        lambda req: json_response([{"id": 1, "name": "default", "is_owner": True}])
    )

    data = await _call_tool("list_search_spaces", {"owned_only": True, "limit": 50})

    assert data == [{"id": 1, "name": "default", "is_owner": True}]
    assert len(recorded) == 1
    req = recorded[0]
    assert req.url.path == "/api/v1/searchspaces"
    assert req.url.params["owned_only"] == "true"
    assert req.url.params["limit"] == "50"
    assert req.url.params["skip"] == "0"
    _assert_bearer(req)


async def test_search_documents(mock_transport) -> None:
    recorded = mock_transport(
        lambda req: json_response({"items": [{"id": 42, "title": "Q3 roadmap"}], "total": 1})
    )

    data = await _call_tool(
        "search_documents",
        {"title": "roadmap", "search_space_id": 7, "page_size": 5},
    )

    assert data["items"][0]["id"] == 42
    req = recorded[0]
    assert req.url.path == "/api/v1/documents/search"
    assert req.url.params["title"] == "roadmap"
    assert req.url.params["search_space_id"] == "7"
    assert req.url.params["page_size"] == "5"
    _assert_bearer(req)


async def test_get_document(mock_transport) -> None:
    recorded = mock_transport(
        lambda req: json_response({"id": 42, "title": "Q3 roadmap", "content": "..."})
    )

    data = await _call_tool("get_document", {"document_id": 42})

    assert data["id"] == 42
    req = recorded[0]
    assert req.url.path == "/api/v1/documents/42"
    _assert_bearer(req)


async def test_get_recent_documents(mock_transport) -> None:
    recorded = mock_transport(
        lambda req: json_response({"items": [], "total": 0, "page": 1, "page_size": 5})
    )

    await _call_tool("get_recent_documents", {"search_space_id": 7, "limit": 5})

    req = recorded[0]
    assert req.url.path == "/api/v1/documents"
    assert req.url.params["search_space_id"] == "7"
    assert req.url.params["sort_by"] == "created_at"
    assert req.url.params["sort_order"] == "desc"
    assert req.url.params["page_size"] == "5"
    _assert_bearer(req)


async def test_list_research_threads(mock_transport) -> None:
    recorded = mock_transport(
        lambda req: json_response({"threads": [], "archived_threads": []})
    )

    await _call_tool("list_research_threads", {"search_space_id": 7, "limit": 25})

    req = recorded[0]
    assert req.url.path == "/api/v1/threads"
    assert req.url.params["search_space_id"] == "7"
    assert req.url.params["limit"] == "25"
    _assert_bearer(req)


async def test_get_research_thread(mock_transport) -> None:
    recorded = mock_transport(lambda req: json_response({"id": 99, "messages": []}))

    data = await _call_tool("get_research_thread", {"thread_id": 99})

    assert data["id"] == 99
    req = recorded[0]
    assert req.url.path == "/api/v1/threads/99"
    _assert_bearer(req)


async def test_upstream_401_surfaces_as_tool_error(mock_transport) -> None:
    mock_transport(lambda req: httpx.Response(401, json={"detail": "Unauthorized"}))

    mcp = get_stdio_mcp()
    async with Client(mcp) as client:
        with pytest.raises(Exception) as exc_info:
            await client.call_tool("get_document", {"document_id": 1})

    assert "401" in str(exc_info.value) or "Unauthorized" in str(exc_info.value)
