"""Bound upload bodies and reject cross-origin browser mutations before spooling."""

from typing import Any

from fastapi import HTTPException, Request
from starlette.responses import JSONResponse


class UploadLimitMiddleware:
    def __init__(self, app: Any, settings: Any):
        self.app = app
        self.settings = settings

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        data_request = scope["type"] == "http" and any(
            scope["path"] == self.settings.api_prefix + path
            or scope["path"].startswith(self.settings.api_prefix + path + "/")
            for path in ("/datasets", "/analyses", "/assistant")
        )
        bounded_receive = receive
        if data_request and scope["method"] not in ("GET", "HEAD", "OPTIONS"):
            headers = dict(scope["headers"])
            origin = headers.get(b"origin")
            if headers.get(b"sec-fetch-site") == b"cross-site" or (
                origin is not None
                and origin.decode("latin-1").rstrip("/") != str(Request(scope).base_url).rstrip("/")
            ):
                await JSONResponse(
                    {"detail": {"code": "ORIGIN_REJECTED", "message": "请从本站页面提交数据或任务"}},
                    status_code=403,
                    headers={"Cache-Control": "no-store"},
                )(scope, receive, send)
                return
        if (
            data_request
            and scope["method"] == "POST"
            and (
                scope["path"] == self.settings.api_prefix + "/datasets"
                or scope["path"].startswith(self.settings.api_prefix + "/assistant/")
            )
        ):
            limit = (
                self.settings.max_upload_bytes + 65_536
                if scope["path"] == self.settings.api_prefix + "/datasets"
                else 65_536
            )
            headers = dict(scope["headers"])
            try:
                length = int(headers.get(b"content-length", b"-1"))
            except ValueError:
                length = -1
            status = 411 if length < 0 else 413 if length > limit else 0
            if status:
                message = "上传必须声明 Content-Length" if status == 411 else "上传请求超过大小上限"
                await JSONResponse(
                    {"detail": {"code": "UPLOAD_LIMIT", "message": message}},
                    status_code=status,
                    headers={"Cache-Control": "no-store"},
                )(scope, receive, send)
                return
            received = 0

            async def bounded_receive() -> dict:
                nonlocal received
                message = await receive()
                received += len(message.get("body", b""))
                if received > limit:
                    raise HTTPException(
                        status_code=413, detail={"code": "UPLOAD_LIMIT", "message": "上传请求超过大小上限"}
                    )
                return message

        async def data_send(message: dict) -> None:
            if data_request and message["type"] == "http.response.start":
                headers = [
                    (key, value) for key, value in message.get("headers", []) if key != b"cache-control"
                ]
                message["headers"] = [*headers, (b"cache-control", b"no-store")]
            await send(message)

        await self.app(scope, bounded_receive, data_send)
