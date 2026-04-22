# SurfSense MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io) server that exposes a SurfSense knowledge base to any MCP-compatible client (Claude Desktop, Cursor, VS Code, Windsurf, …).

The v1 surface is **read-only** — it lets external AI tools list search spaces, search documents by title, fetch documents, and read past research threads. Semantic search and the `quick_research` / `deep_research` / `summarize` / `compare` / `extract_facts` tools are deliberately deferred because they require new backend endpoints in `surfsense_backend`.

## Tools

| Tool | Description |
|---|---|
| `list_search_spaces` | List the search spaces the authenticated user can access. |
| `search_documents` | Keyword search on document titles within a search space (ILIKE, not semantic). |
| `get_document` | Fetch a document by ID, including content and metadata. |
| `get_recent_documents` | List recently updated documents in a search space (newest first). |
| `list_research_threads` | List chat/research threads in a search space (active + archived). |
| `get_research_thread` | Fetch a thread with its full message history. |

## Authentication

SurfSense currently issues only short-lived JWTs — there is no long-lived API-key concept. This server therefore accepts a pre-obtained JWT and forwards it as `Authorization: Bearer <jwt>` on every upstream call.

**How to obtain a JWT:** log in to your SurfSense instance in a browser, open DevTools → Network, and copy the `Authorization` header from any request to the backend (or pull it from `localStorage`). When the token expires, repeat.

## Install

```bash
cd surfsense-mcp-server
uv pip install -e ".[dev]"
```

## Run — stdio (local, recommended)

```bash
SURFSENSE_BASE_URL=https://foss-research.local.moneta.dev \
SURFSENSE_JWT=<paste-jwt-here> \
python -m surfsense_mcp stdio
```

## Run — HTTP (remote)

```bash
python -m surfsense_mcp http   # binds 0.0.0.0:8211
```

Clients supply the JWT via the `Authorization: Bearer …` header. The server validates it by calling `GET {SURFSENSE_BASE_URL}/users/me` on the upstream SurfSense API.

## MCP Client Config

### Claude Desktop / Cursor (stdio)

```json
{
  "mcpServers": {
    "surfsense": {
      "command": "uvx",
      "args": ["surfsense-mcp-server", "stdio"],
      "env": {
        "SURFSENSE_BASE_URL": "https://foss-research.local.moneta.dev",
        "SURFSENSE_JWT": "<paste-jwt-here>"
      }
    }
  }
}
```

### Remote HTTP

```json
{
  "mcpServers": {
    "surfsense": {
      "command": "npx",
      "args": ["mcp-remote@latest", "http://localhost:8211/mcp"],
      "headers": {
        "Authorization": "Bearer <jwt>"
      }
    }
  }
}
```

## Configuration

| Variable | Required | Purpose |
|---|---|---|
| `SURFSENSE_BASE_URL` | yes (all modes) | Base URL of the SurfSense backend (no trailing slash). |
| `SURFSENSE_JWT` | yes (stdio only) | JWT forwarded as `Authorization: Bearer`. In HTTP mode the token is taken from the request header. |

## Development

```bash
# Lint & format
ruff check surfsense_mcp/
ruff format surfsense_mcp/

# Tests
pytest
```

## Future Work

Tools deferred to a later iteration because they require backend changes in `surfsense_backend`:

- `semantic_search` — needs a new HTTP route exposing `DocumentHybridSearchRetriever` (currently agent-internal).
- `summarize_documents`, `compare_documents`, `extract_facts` — currently only available via the streaming chat agent.
- `quick_research` / `deep_research` — would need SSE-stream consumption against the existing `/api/v1/new_chat` endpoint.
- OAuth / mPass integration — would replace the JWT-paste UX with a proper SSO flow.
