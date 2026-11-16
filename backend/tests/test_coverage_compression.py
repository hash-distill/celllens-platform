import gzip

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.testclient import TestClient

from backend.app.coverage_middleware import CoverageCompressionMiddleware


def catalogue(_request):
    return JSONResponse({"genes": ["ALDOA"] * 500}, headers={"Cache-Control": "no-store"})


def application():
    return CoverageCompressionMiddleware(
        Starlette(
            routes=[
                Route("/api/v1/coverage", catalogue),
                Route("/api/v1/assistant/interpret", catalogue, methods=["POST"]),
                Route("/api/v1/coverage-other", catalogue),
            ]
        ),
        api_prefix="/api/v1",
    )


def test_catalogue_compression_preserves_content_and_private_cache_policy():
    with TestClient(application()) as client:
        compressed = client.get("/api/v1/coverage?cell_line=K562", headers={"Accept-Encoding": "gzip"})
        identity = client.get("/api/v1/coverage", headers={"Accept-Encoding": "identity"})
    assert compressed.json() == identity.json()
    assert compressed.headers["content-encoding"] == "gzip"
    assert "content-encoding" not in identity.headers
    assert compressed.headers["cache-control"] == "no-store"
    assert "Accept-Encoding" in compressed.headers["vary"]
    assert int(compressed.headers["content-length"]) < len(identity.content) / 5


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/api/v1/assistant/interpret"),
        ("GET", "/api/v1/coverage-other"),
    ],
)
def test_other_routes_are_not_compressed(method, path):
    with TestClient(application()) as client:
        response = client.request(method, path, headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 200
    assert "content-encoding" not in response.headers


def test_small_errors_and_existing_encoding_are_preserved():
    async def endpoint(request):
        if request.query_params.get("error"):
            return JSONResponse(
                {"detail": "unavailable"}, status_code=503, headers={"Cache-Control": "no-store"}
            )
        return Response(gzip.compress(b"already encoded"), headers={"Content-Encoding": "gzip"})

    app = CoverageCompressionMiddleware(
        Starlette(routes=[Route("/custom/coverage", endpoint)]),
        api_prefix="/custom/",
    )
    with TestClient(app) as client:
        error = client.get("/custom/coverage?error=1")
        existing = client.get("/custom/coverage")
    assert error.status_code == 503 and error.json() == {"detail": "unavailable"}
    assert error.headers["cache-control"] == "no-store"
    assert "content-encoding" not in error.headers
    assert existing.content == b"already encoded"
