"""SurfSense MCP Server implementation."""

from fastmcp import FastMCP
from fastmcp.server.middleware.logging import StructuredLoggingMiddleware
from mcp.types import Icon

from surfsense_mcp.auth import SurfSenseHeaderAuthProvider
from surfsense_mcp.tools import register_tools


def get_header_mcp() -> FastMCP:
    """HTTP mode — validates Authorization: Bearer header against SurfSense."""
    mcp = FastMCP(
        "SurfSense MCP Server (http)",
        icons=[Icon(src="https://surfsense.net/favicon.ico", alt="SurfSense MCP Server")],
        website_url="https://surfsense.net",
        auth=SurfSenseHeaderAuthProvider(required_scopes=["read"]),
    )
    mcp.add_middleware(StructuredLoggingMiddleware(include_payloads=True))
    register_tools(mcp)
    return mcp


def get_stdio_mcp() -> FastMCP:
    """Stdio mode — uses SURFSENSE_JWT env var for upstream auth."""
    mcp = FastMCP("SurfSense MCP Server (stdio)")
    mcp.add_middleware(StructuredLoggingMiddleware(include_payloads=True))
    register_tools(mcp)
    return mcp
