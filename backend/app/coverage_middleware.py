"""Compress the large, read-only metabolic catalogue without changing other APIs."""

from starlette.middleware.gzip import GZipMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send


class CoverageCompressionMiddleware:
    def __init__(self, app: ASGIApp, api_prefix: str) -> None:
        self.app = app
        self.path = api_prefix.rstrip("/") + "/coverage"
        self.compressed = GZipMiddleware(app, minimum_size=1024, compresslevel=5)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"] == self.path and scope["method"] in {"GET", "HEAD"}:
            await self.compressed(scope, receive, send)
        else:
            await self.app(scope, receive, send)
