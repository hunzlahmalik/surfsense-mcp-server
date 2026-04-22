"""Search space tools for the SurfSense MCP Server."""

from typing import Any

from fastmcp import FastMCP

from surfsense_mcp.client import get_surfsense_client_context


def register_search_space_tools(mcp: FastMCP) -> None:
    """Register search-space tools."""

    @mcp.tool()
    async def list_search_spaces(
        owned_only: bool = False,
        skip: int = 0,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """
        List search spaces the authenticated user can access.

        A search space is a workspace that groups documents, chats, and research
        threads. Most other tools require a `search_space_id`, so this is
        typically the first call.

        Args:
            owned_only: If true, return only spaces the user owns (excludes
                shared spaces they are a member of). Defaults to false.
            skip: Number of items to skip for pagination. Defaults to 0.
            limit: Maximum number of items to return (backend default 200).

        Returns:
            List of search spaces. Each entry contains at least: id, name,
            description, created_at, user_id, citations_enabled,
            qna_custom_instructions, member_count, is_owner.
        """
        ctx = get_surfsense_client_context()
        async with ctx.client as client:
            response = await client.get(
                "/api/v1/searchspaces",
                params={
                    "owned_only": str(owned_only).lower(),
                    "skip": skip,
                    "limit": limit,
                },
            )
            response.raise_for_status()
            return response.json()
