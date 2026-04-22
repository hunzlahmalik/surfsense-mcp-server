"""Document tools for the SurfSense MCP Server."""

from typing import Any

from fastmcp import FastMCP

from surfsense_mcp.client import get_surfsense_client_context


def register_document_tools(mcp: FastMCP) -> None:
    """Register document tools."""

    @mcp.tool()
    async def search_documents(
        title: str,
        search_space_id: int | None = None,
        document_types: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """
        Search documents by title substring (case-insensitive keyword match).

        This is NOT semantic search — it performs a simple ILIKE on the
        document title column. Use it to find documents by known title
        fragments, not to explore topics.

        Args:
            title: Title substring to search for (required).
            search_space_id: Restrict results to a single search space. If
                omitted, searches across all spaces the user can access.
            document_types: Comma-separated document type filter (e.g.
                "EXTENSION,FILE,SLACK_CONNECTOR").
            page: 1-based page number. Defaults to 1.
            page_size: Results per page (1-100). Defaults to 20.

        Returns:
            Paginated response with keys: items (list of documents), total,
            page, page_size, has_next, has_prev.
        """
        params: dict[str, Any] = {"title": title, "page": page, "page_size": page_size}
        if search_space_id is not None:
            params["search_space_id"] = search_space_id
        if document_types:
            params["document_types"] = document_types

        ctx = get_surfsense_client_context()
        async with ctx.client as client:
            response = await client.get("/api/v1/documents/search", params=params)
            response.raise_for_status()
            return response.json()

    @mcp.tool()
    async def get_document(document_id: int) -> dict[str, Any]:
        """
        Retrieve a single document by its ID, including content and metadata.

        Args:
            document_id: The integer document ID (as returned by
                search_documents or get_recent_documents).

        Returns:
            A document object containing at least: id, title, document_type,
            document_metadata, content, content_hash, search_space_id,
            folder_id, created_at, updated_at, status.
        """
        ctx = get_surfsense_client_context()
        async with ctx.client as client:
            response = await client.get(f"/api/v1/documents/{document_id}")
            response.raise_for_status()
            return response.json()

    @mcp.tool()
    async def get_recent_documents(
        search_space_id: int | None = None,
        document_types: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """
        List recently created documents, newest first.

        Thin wrapper over the list-documents endpoint with sort_by=created_at
        and sort_order=desc enforced. The SurfSense backend does not support
        sorting by updated_at, so "recent" here means recently created.

        Args:
            search_space_id: Restrict to one search space. Omit to list across
                all accessible spaces.
            document_types: Comma-separated document type filter.
            limit: Maximum number of documents to return (1-100). Defaults to 20.

        Returns:
            Paginated response with items, total, page, page_size, has_next,
            has_prev.
        """
        params: dict[str, Any] = {
            "page": 1,
            "page_size": max(1, min(limit, 100)),
            "sort_by": "created_at",
            "sort_order": "desc",
        }
        if search_space_id is not None:
            params["search_space_id"] = search_space_id
        if document_types:
            params["document_types"] = document_types

        ctx = get_surfsense_client_context()
        async with ctx.client as client:
            response = await client.get("/api/v1/documents", params=params)
            response.raise_for_status()
            return response.json()
