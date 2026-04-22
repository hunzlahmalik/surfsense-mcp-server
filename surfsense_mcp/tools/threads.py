"""Research-thread (chat) tools for the SurfSense MCP Server."""

from typing import Any

from fastmcp import FastMCP

from surfsense_mcp.client import get_surfsense_client_context


def register_thread_tools(mcp: FastMCP) -> None:
    """Register research-thread tools."""

    @mcp.tool()
    async def list_research_threads(
        search_space_id: int,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """
        List chat/research threads in a search space (active + archived).

        SurfSense's "research" surface is its chat agent; every chat thread is
        effectively a research session, so this tool covers the
        research_history use case.

        Args:
            search_space_id: The search space to list threads for (required).
            limit: Optional cap on active threads returned. Archived threads
                are always returned in full.

        Returns:
            Object with keys: threads (active, list of thread summaries) and
            archived_threads (list of archived thread summaries). Each thread
            summary contains: id, title, archived, visibility, created_by_id,
            is_own_thread, created_at, updated_at.
        """
        params: dict[str, Any] = {"search_space_id": search_space_id}
        if limit is not None:
            params["limit"] = limit

        ctx = get_surfsense_client_context()
        async with ctx.client as client:
            response = await client.get("/api/v1/threads", params=params)
            response.raise_for_status()
            return response.json()

    @mcp.tool()
    async def get_research_thread(thread_id: int) -> dict[str, Any]:
        """
        Retrieve a single research thread including its full message history.

        Args:
            thread_id: The integer thread ID (as returned by
                list_research_threads).

        Returns:
            Thread object with messages list. Each message has: id, role
            (user|assistant|system), content (rich JSONB), thread_id,
            author_id, created_at.
        """
        ctx = get_surfsense_client_context()
        async with ctx.client as client:
            response = await client.get(f"/api/v1/threads/{thread_id}")
            response.raise_for_status()
            return response.json()
