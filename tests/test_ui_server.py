"""The web screen's server: serves the built app and forwards only the screen's endpoints to the API."""

from __future__ import annotations

import httpx
import pytest
from starlette.testclient import TestClient

from app.ingestion.readers import spreadsheet_rows
from app.ui import server


@pytest.fixture
def web(tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>crossexam</html>")
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log('hi')")
    (tmp_path / "assets" / "font.woff2").write_bytes(b"wOF2")
    seen: list[httpx.Request] = []

    def api(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True}, headers={"X-Export-Rows": "3", "Set-Cookie": "session=leak"})

    monkeypatch.setattr(server, "DIST", tmp_path.resolve())
    monkeypatch.setattr(server, "client", httpx.AsyncClient(transport=httpx.MockTransport(api)))
    with TestClient(server.app) as client:
        yield client, seen


def test_router_paths_get_the_app_and_assets_are_cached(web):
    client, _ = web
    page = client.get("/review/some-pack-id")
    assert page.status_code == 200 and "crossexam" in page.text
    assert page.headers["cache-control"] == "no-cache"
    asset = client.get("/assets/index-abc123.js")
    assert asset.status_code == 200 and "immutable" in asset.headers["cache-control"]
    assert client.get("/assets/font.woff2").headers["content-type"] == "font/woff2"
    assert client.get("/assets/missing.js").status_code == 404


def test_proxy_forwards_identity_query_and_body(web):
    client, seen = web
    r = client.post("/api/packs/p1/decisions?dry=1", json={"decisions": []},
                    headers={"X-User": "meena", "X-Role": "finance_manager", "Cookie": "private=1"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert r.headers["x-export-rows"] == "3" and "set-cookie" not in r.headers
    sent = seen[0]
    assert sent.method == "POST" and sent.url.path == "/packs/p1/decisions" and sent.url.query == b"dry=1"
    assert sent.headers["x-user"] == "meena" and sent.headers["x-role"] == "finance_manager"
    assert "cookie" not in sent.headers and "authorization" not in sent.headers
    assert sent.content == b'{"decisions":[]}'


@pytest.mark.parametrize("path", ["/api/admin/reap-stale", "/api/metrics", "/api/readyz"])
def test_internal_endpoints_are_not_reachable_from_the_browser(web, path):
    client, seen = web
    assert client.post(path).status_code == 404
    assert seen == []


def test_api_down_is_a_clear_502(web, monkeypatch):
    client, _ = web

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    monkeypatch.setattr(server, "client", httpx.AsyncClient(transport=httpx.MockTransport(down)))
    r = client.get("/api/batches")
    assert r.status_code == 502 and "unreachable" in r.json()["detail"]


def test_spreadsheet_rows_for_the_screen():
    sheets = spreadsheet_rows("packing.csv", b"sku,qty\nSKU-1,250\nSKU-2,\n", max_rows=2)
    assert sheets == [{"name": "Sheet1", "rows": [["sku", "qty"], ["SKU-1", "250"]], "truncated": True}]
