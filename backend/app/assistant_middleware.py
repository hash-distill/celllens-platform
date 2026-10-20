"""Bound assistant requests and reject cross-origin browser mutations."""

from typing import Any

from fastapi import HTTPException, Request
from starlette.responses import JSONResponse


class AssistantRequestMiddleware:
    def __init__(self, app: Any, api_prefix: str):
        self.app = app
        self.prefix = api_prefix + "/assistant"

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        assistant = scope["type"] == "http" and (
            scope["path"] == self.prefix or scope["path"].startswith(self.prefix + "/")
        )
        bounded_receive = receive
        if assistant and scope["method"] not in ("GET", "HEAD", "OPTIONS"):
            headers = dict(scope["headers"])
            origin = headers.get(b"origin")
            if headers.get(b"sec-fetch-site") == b"cross-site" or (
                origin is not None
                and origin.decode("latin-1").rstrip("/") != str(Request(scope).base_url).rstrip("/")
            ):
                await JSONResponse(
                    {"detail": {"code": "ORIGIN_REJECTED", "message": "请从本站页面提交解读请求"}},
                    status_code=403,
                    headers={"Cache-Control": "no-store"},
                )(scope, receive, send)
                return
        if assistant and scope["method"] == "POST":
            try:
                length = int(dict(scope["headers"]).get(b"content-length", b"-1"))
            except ValueError:
                length = -1
            status = 411 if length < 0 else 413 if length > 65_536 else 0
            if status:
                await JSONResponse(
                    {"detail": {"code": "ASSISTANT_REQUEST_LIMIT", "message": "请求缺少长度或超过大小上限"}},
                    status_code=status,
                    headers={"Cache-Control": "no-store"},
                )(scope, receive, send)
                return
            received = 0

            async def bounded_receive() -> dict:
                nonlocal received
                message = await receive()
                received += len(message.get("body", b""))
                if received > 65_536:
                    raise HTTPException(
                        413,
                        detail={
                            "code": "ASSISTANT_REQUEST_LIMIT",
                            "message": "解读请求超过大小上限",
                        },
                    )
                return message

        async def assistant_send(message: dict) -> None:
            if assistant and message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", []) if k != b"cache-control"]
                message["headers"] = [*headers, (b"cache-control", b"no-store")]
            await send(message)

        await self.app(scope, bounded_receive, assistant_send)
