# CLAUDE.md — surfsense-mcp-server

## What this package is

A [FastMCP v3](https://gofastmcp.com) server that exposes SurfSense as MCP tools (read + write + streaming chat). It is a sibling to `plane-mcp-server/` and follows the same structure.

**No backend changes to SurfSense are allowed** — all tools call existing `surfsense_backend` HTTP routes. Tools may use any HTTP verb the route supports (GET/POST/PUT/DELETE).

## Package layout

```
surfsense-mcp-server/
├── pyproject.toml
├── README.md
├── CLAUDE.md                              ← this file
├── .env.example
├── surfsense_mcp/
│   ├── __init__.py
│   ├── __main__.py                        # CLI entry: ServerMode enum (stdio|http), JSON logging
│   ├── server.py                          # get_stdio_mcp() / get_header_mcp() factories
│   ├── client.py                          # get_surfsense_client_context() → httpx.AsyncClient
│   ├── auth/
│   │   ├── __init__.py
│   │   └── surfsense_header_auth_provider.py  # TokenVerifier — validates JWT via GET /users/me
│   └── tools/
│       ├── __init__.py                    # register_tools(mcp) — calls all per-module register fns
│       ├── search_spaces.py               # list / get / create / update / delete
│       ├── documents.py                   # list / search / get / upload / update / delete / status / type_counts
│       ├── threads.py                     # list / get / delete / history + query (SSE streaming)
│       ├── reports.py                     # list / get / export / delete
│       ├── notes.py                       # create
│       └── logs.py                        # get
└── tests/
    ├── conftest.py                        # mock_transport fixture, FAKE_JWT, json_response
    └── test_tools.py                      # 7 smoke tests — URL, query string, auth header, 401
```

## Dev commands

```bash
# Install
cd surfsense-mcp-server
uv venv && uv pip install -e ".[dev]"

# Tests (no live backend needed — httpx is mocked)
pytest

# Lint / format
ruff check surfsense_mcp/
ruff format surfsense_mcp/

# Upgrade fastmcp to latest v3
uv sync --extra dev --upgrade-package fastmcp

# Run stdio locally (JWT paste)
SURFSENSE_BASE_URL=http://localhost:8000 SURFSENSE_JWT=<jwt> python -m surfsense_mcp stdio

# Run stdio with password fallback (no JWT paste)
SURFSENSE_BASE_URL=http://localhost:8000 \
SURFSENSE_EMAIL=admin@example.com SURFSENSE_PASSWORD=<pw> \
python -m surfsense_mcp stdio

# Run HTTP mode
SURFSENSE_BASE_URL=http://localhost:8000 python -m surfsense_mcp http   # binds :8211
```

## Architecture

### Transport modes

- **stdio** — used by Claude Desktop / Cursor / VS Code. `SURFSENSE_JWT` env var carries the token. `get_stdio_mcp()` builds a FastMCP instance without an auth provider; the JWT is read directly from env in `client.py`.
- **http** — for remote deploys. `get_header_mcp()` attaches `SurfSenseHeaderAuthProvider` which validates each request's `Authorization: Bearer` header against `GET /users/me`. CORS is configured via `http_app(middleware=[...])`. Port: `8211`.

### Auth model

SurfSense issues short-lived JWTs from `fastapi-users` (no API-key concept). Two input paths are supported; the stdio password fallback is optional.

- **stdio (primary):** JWT from `SURFSENSE_JWT` env var — user pastes a fresh one when it expires. No refresh.
- **stdio (optional fallback):** if `SURFSENSE_JWT` is unset and `SURFSENSE_EMAIL` + `SURFSENSE_PASSWORD` are set, the client calls `POST /auth/jwt/login`, caches the token for `TOKEN_TTL` seconds (default 3300 = 55 min), and auto-re-authenticates once on 401. Intended for CI / long-running stdio sessions.
- **http:** JWT from `Authorization: Bearer` request header; validated by `SurfSenseHeaderAuthProvider` calling `GET /users/me`. Password fallback is **not** enabled in HTTP mode — the Bearer identity must come from the caller.

`get_surfsense_client_context()` in `client.py` resolves the token in this order: FastMCP request-scoped `get_access_token()` → `SURFSENSE_JWT` env → password login (if creds present). On 401 in password mode only, re-authenticate once and retry; otherwise raise.

### Tool conventions

- Every tool is decorated with `@mcp.tool()` and registered via a `register_*` function called from `tools/__init__.py:register_tools()`.
- Tools return raw `dict` / `list` — no Pydantic re-modeling of SurfSense's response schemas.
- Tools `raise` on non-2xx responses so FastMCP surfaces errors to the MCP client.
- All tools open and close `httpx.AsyncClient` within the call using an `async with` block (client is not shared across calls).
- Write tools (POST/PUT/DELETE) are allowed. Follow SurfSense's existing request schemas — do **not** introduce new fields.
- Chat/query tools consume SSE from `POST /api/v1/new_chat` via `httpx.AsyncClient.stream(...)`. Parse `text-delta` events (and the documented control events: `start`, `start-step`, `finish`, `finish-step`, `text-start`, `text-end`, `data-thinking-step`, `data-thread-title-update`) into a single concatenated string; fall back to raw JSON / raw text when the event shape is unknown. See DocuMentor's `_query_surfsense` for the reference event taxonomy.
- Tools that create a thread on demand (when `thread_id` is `None`) must `POST /api/v1/threads` first, then stream, and return the new `thread_id` so callers can continue the conversation.
- Binary/export responses (e.g. `GET /api/v1/reports/{id}/export`) return content-type + size, not inline bytes.

### FastMCP version

Requires **fastmcp >= 3.0.0, < 4.0.0**. The v3 HTTP mode API differs from v2:

```python
# v3 — correct
header_app = header_mcp.http_app(middleware=cors, stateless_http=True)
app = Starlette(routes=[Mount("/", app=header_app)], lifespan=header_app.lifespan)

# v2 — do NOT use
app = header_mcp.http_app(middleware=cors)  # different signature
```

`lifespan` must be `header_app.lifespan` (not a lambda wrapping it).

## Key constraints

- **No backend changes** — all tools must call routes that already exist in `surfsense_backend`. Verify in `surfsense_backend/app/routes/` before adding any tool. If a route is missing, drop the tool — do not add one to the backend.
- **No new MCP resources** — tools only.
- **No Pydantic re-modeling** — return raw dicts from httpx responses. SurfSense's schemas are not imported here.
- **No token refresh in JWT-paste mode** — the server does not attempt to refresh `SURFSENSE_JWT`. Expiry surfaces to the MCP client as a 401. Password-fallback mode is the only path with auto-reauth.
- **HTTP mode never uses password login** — only stdio is allowed to log in with email/password, to keep the Bearer-validated HTTP surface identity-bound to the caller.

## Relevant SurfSense backend files

When adding tools, check these backend files to confirm route paths and query parameters:

| Backend file | What it defines |
|---|---|
| `surfsense_backend/app/routes/search_space_routes.py` | `/api/v1/searchspaces` (list/get/create/update/delete) — list supports `owned_only`, `skip`, `limit` |
| `surfsense_backend/app/routes/documents_routes.py` | `/api/v1/documents`, `/documents/search`, `/documents/{id}` (GET/PUT/DELETE), `/documents/fileupload`, `/documents/status`, `/documents/type-counts` |
| `surfsense_backend/app/routes/threads_routes.py` | `/api/v1/threads`, `/threads/{id}`, `/threads/{id}/messages`, `POST /api/v1/new_chat` (SSE stream) |
| `surfsense_backend/app/routes/reports_routes.py` | `/api/v1/reports`, `/reports/{id}/content`, `/reports/{id}/export` |
| `surfsense_backend/app/routes/logs_routes.py` | `/api/v1/logs` |
| `surfsense_backend/app/routes/notes_routes.py` | `POST /api/v1/search-spaces/{id}/notes` |
| `surfsense_backend/app/routes/auth_routes.py` | `/users/me`, `POST /auth/jwt/login` |

> `sort_column_map` in `documents_routes.py` only accepts `"created_at"`, `"title"`, `"document_type"` — `"updated_at"` is not a valid sort key.
>
> Confirm each route's existence and exact path before implementing a tool — DocuMentor (the reference port source) targets a different SurfSense fork and some paths may not match this fork. If a route is missing, drop the tool (no backend additions).

## Test fixtures

`tests/conftest.py` provides:

- `mock_transport` — patches `httpx.AsyncClient.__init__` with a `MockTransport`. Returns a `setup(handler)` callable; calling it registers a response handler and returns a `recorded: list[httpx.Request]` for assertion.
- `_env` (autouse) — sets `SURFSENSE_BASE_URL` and `SURFSENSE_JWT` per test via `monkeypatch`.
- `json_response(payload, status_code=200)` — helper to build `httpx.Response` from a dict.

Tests use `Client(get_stdio_mcp())` (FastMCP in-process client) — no subprocess, no network.

## SurfSense backend port

The default SurfSense backend port is `8000` (`UVICORN_PORT`). Instances vary — confirm with the operator before hardcoding. In the Moneta devstack it may run on a different port (e.g. `8929`).
