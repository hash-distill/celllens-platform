"""Reject unbounded multipart requests before Starlette spools their body."""

import asyncio
import hmac
from http.cookies import CookieError, SimpleCookie
from typing import Any

from fastapi import HTTPException
from starlette.responses import JSONResponse

from backend.app.user_data.auth import COOKIE_NAME


class UploadLimitMiddleware:
    def __init__(self, app: Any, settings: Any):
        self.app = app
        self.settings = settings

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        bounded_receive = receive
        if (
            scope["type"] == "http"
            and scope["method"] == "POST"
            and (scope["path"] == self.settings.api_prefix + "/datasets")
        ):
            headers = dict(scope["headers"])
            try:
                length = int(headers.get(b"content-length", b"-1"))
            except ValueError:
                length = -1
            status = 411 if length < 0 else 413 if length > self.settings.max_upload_bytes + 65_536 else 0
            if status:
                message = "上传必须声明 Content-Length" if status == 411 else "上传请求超过大小上限"
                await JSONResponse(
                    {"detail": {"code": "UPLOAD_LIMIT", "message": message}}, status_code=status
                )(scope, receive, send)
                return
            # Authenticate before the framework parses or spools an upload body.
            cookie = SimpleCookie()
            try:
                cookie.load(headers.get(b"cookie", b"").decode("latin-1"))
            except CookieError:
                pass
            ticket = cookie.get(COOKIE_NAME)
            token = ticket.value if ticket else ""
            store = scope["app"].state.container.user_store
            user = await asyncio.to_thread(store.authenticate, token)
            if user is None:
                await JSONResponse(
                    {"detail": {"code": "LOGIN_REQUIRED", "message": "请先登录"}}, status_code=401
                )(scope, receive, send)
                return
            if not hmac.compare_digest(headers.get(b"x-csrf-token", b""), user["csrf_token"].encode()):
                await JSONResponse(
                    {"detail": {"code": "CSRF_REQUIRED", "message": "会话校验失败"}}, status_code=403
                )(scope, receive, send)
                return
            received = 0

            async def bounded_receive() -> dict:
                nonlocal received
                message = await receive()
                received += len(message.get("body", b""))
                if received > self.settings.max_upload_bytes + 65_536:
                    raise HTTPException(
                        status_code=413, detail={"code": "UPLOAD_LIMIT", "message": "上传请求超过大小上限"}
                    )
                return message

        private = scope["type"] == "http" and any(
            scope["path"].startswith(self.settings.api_prefix + path)
            for path in ("/auth/", "/datasets", "/analyses")
        )

        async def private_send(message: dict) -> None:
            if private and message["type"] == "http.response.start":
                headers = [
                    (key, value) for key, value in message.get("headers", []) if key != b"cache-control"
                ]
                message["headers"] = [*headers, (b"cache-control", b"no-store")]
            await send(message)

        await self.app(scope, bounded_receive, private_send)
