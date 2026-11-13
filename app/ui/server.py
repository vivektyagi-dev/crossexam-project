"""The web screen's server: serves the built React app (web/dist) and forwards /api/* to the
FastAPI service. The browser never talks to the API directly, so on Google Cloud the API stays
private: this server attaches a Google identity token for the web service account.

Only the endpoints the screen uses are forwarded; /admin and /metrics stay internal.

    cd web && npm ci && npm run build
    uvicorn app.ui.server:app --port 8080
"""

from __future__ import annotations

import mimetypes
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse, Response, StreamingResponse
from starlette.routing import Route

API = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
DIST = Path(os.environ.get("WEB_DIST", Path(__file__).resolve().parents[2] / "web" / "dist")).resolve()

mimetypes.add_type("font/woff2", ".woff2")  # not in Python's default table: fonts would go out as text/plain
mimetypes.add_type("font/woff", ".woff")

ALLOWED_PREFIXES = {"batches", "packs", "documents", "exports", "outbox", "stats"}
FORWARD_REQUEST = {"accept", "content-type", "content-length", "x-user", "x-role", "traceparent"}
FORWARD_RESPONSE = {"content-type", "content-disposition", "x-export-rows"}
TOKEN_TTL_SECONDS = 1800  # identity tokens last an hour

client = httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0))
_token: tuple[str, float] | None = None


def _fetch_id_token() -> str:
    import google.auth.transport.requests
    import google.oauth2.id_token

    return google.oauth2.id_token.fetch_id_token(google.auth.transport.requests.Request(), API)


async def id_token() -> str | None:
    """On Cloud Run the API only accepts callers with a Google identity token."""
    global _token
    if os.environ.get("API_AUTH") != "gcp":
        return None
    if _token is None or time.monotonic() - _token[1] > TOKEN_TTL_SECONDS:
        _token = (await run_in_threadpool(_fetch_id_token), time.monotonic())
    return _token[0]


async def proxy(request: Request) -> Response:
    path = request.path_params["path"]
    if path.split("/", 1)[0] not in ALLOWED_PREFIXES:
        return JSONResponse({"detail": "Not found"}, status_code=404)
    url = f"{API}/{path}" + (f"?{request.url.query}" if request.url.query else "")
    headers = {k: v for k, v in request.headers.items() if k.lower() in FORWARD_REQUEST}
    token = await id_token()
    if token:
        headers["authorization"] = f"Bearer {token}"
    body = request.stream() if request.method in ("POST", "PUT", "PATCH") else None
    try:
        upstream = await client.send(client.build_request(request.method, url, headers=headers, content=body), stream=True)
    except httpx.HTTPError as exc:
        return JSONResponse({"detail": f"The API is unreachable ({exc.__class__.__name__})."}, status_code=502)
    return StreamingResponse(
        upstream.aiter_bytes(),
        status_code=upstream.status_code,
        headers={k: v for k, v in upstream.headers.items() if k.lower() in FORWARD_RESPONSE},
        background=BackgroundTask(upstream.aclose),
    )


async def spa(request: Request) -> Response:
    """Built files as they are; any other path gets index.html so the router can handle it."""
    rel = request.path_params.get("path", "")
    target = (DIST / rel).resolve()
    if rel and target.is_file() and DIST in target.parents:
        immutable = rel.startswith("assets/")  # hashed names: safe to cache forever
        return FileResponse(target, headers={"Cache-Control": "public, max-age=31536000, immutable" if immutable
                                             else "no-cache"})
    if rel.startswith("assets/"):
        return PlainTextResponse("Not found", status_code=404)
    index = DIST / "index.html"
    if not index.is_file():
        return PlainTextResponse("The web screen is not built yet: run `npm ci && npm run build` in web/.",
                                 status_code=503)
    return FileResponse(index, headers={"Cache-Control": "no-cache"})


async def healthz(_request: Request) -> Response:
    return JSONResponse({"ok": True})


@asynccontextmanager
async def lifespan(_app: Starlette):
    yield
    await client.aclose()


app = Starlette(
    routes=[
        Route("/healthz", healthz),
        Route("/api/{path:path}", proxy, methods=["GET", "POST", "PUT", "PATCH", "DELETE"]),
        Route("/{path:path}", spa),
    ],
    lifespan=lifespan,
)
