"""Single-workspace access policy. This is not a multi-user authorization model."""

import hashlib
import hmac
import json
import re
import time
from collections.abc import AsyncIterable
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

COOKIE = "celllens_workspace"
router = APIRouter(prefix="/auth", tags=["workspace access"])


def local_request(request):
    return bool(request.client and request.client.host in {"127.0.0.1", "::1", "testclient"})


def local_host_allowed(request):
    # A loopback peer alone does not prevent browser DNS rebinding.
    hosts = request.headers.getlist("host")
    if len(hosts) != 1:
        return False
    try:
        authority = urlsplit("//" + hosts[0])
        port = authority.port
    except ValueError:
        return False
    if authority.username is not None or authority.password is not None:
        return False
    if (
        authority.path
        or authority.query
        or authority.fragment
        or (port is not None and not 1 <= port <= 65535)
    ):
        return False
    allowed = {"localhost", "127.0.0.1", "::1"}
    # ASGI TestClient has a synthetic peer, which cannot occur on a TCP socket.
    if request.client and request.client.host == "testclient":
        allowed.add("testserver")
    return authority.hostname in allowed


def session_value(settings, expiry):
    value = str(expiry)
    signature = hmac.new(settings.workspace_token.encode(), value.encode(), hashlib.sha256).hexdigest()
    return f"{value}.{signature}"


def authenticated(request, settings):
    if settings.deployment_mode == "public":
        return False
    if settings.deployment_mode == "local":
        return local_request(request)
    if not settings.workspace_token:
        return False
    bearer = request.headers.get("authorization", "")
    if bearer.startswith("Bearer ") and hmac.compare_digest(
        bearer[7:].encode(), settings.workspace_token.encode()
    ):
        return True
    cookie = request.cookies.get(COOKIE, "")
    try:
        expiry = int(cookie.split(".", 1)[0])
    except ValueError:
        return False
    return expiry >= int(time.time()) and hmac.compare_digest(
        cookie.encode(), session_value(settings, expiry).encode()
    )


def public_ids(settings):
    return {
        value.strip()
        for value in settings.public_result_ids.split(",")
        if re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value.strip())
    }


def same_origin_request(request):
    origin = request.headers.get("origin")
    if request.headers.get("sec-fetch-site") == "cross-site":
        return False
    if not origin:
        return True
    try:
        parsed = urlsplit(origin)
        current = urlsplit(str(request.base_url))
    except ValueError:
        return False
    return (parsed.scheme, parsed.netloc) == (current.scheme, current.netloc)


def public_path(path, settings):
    ids = public_ids(settings)
    # Only frozen readers are exposed. Cell-state reconstruction, comparative
    # computation, LLM calls, installation, imports and private notes are absent.
    patterns = (
        r"/research/results/(?:measured|prediction)/([^/]+)(?:/(?:export|projection))?",
        r"/runs/([^/]+)(?:/(?:summary|projection|genes|metabolic-tasks|task-trace|reactions|provenance))?",
        r"/measured/analyses/([^/]+)(?:/(?:table|projection))?",
    )
    return any((match := re.fullmatch(pattern, path)) and match.group(1) in ids for pattern in patterns)


def frozen_result(request, path):
    container = request.app.state.container
    parts = path.strip("/").split("/")
    try:
        if parts[:2] == ["measured", "analyses"] or parts[:3] == ["research", "results", "measured"]:
            identifier = parts[2] if parts[0] == "measured" else parts[3]
            row, digest = request.app.state.measured.store.get(identifier)
            return row["status"] == "completed" and bool(digest)
        identifier = parts[1] if parts[0] == "runs" else parts[3]
        row = container.store.get(identifier)
        return (
            row.status.value == "completed"
            and (container.settings.derived_root / identifier / "manifest.json").is_file()
        )
    except (KeyError, IndexError, OSError):
        return False


def public_records(request):
    """Only registered, completed records; no private failure text or attempt history."""
    container = request.app.state.container
    rows = []
    for identifier in sorted(public_ids(container.settings)):
        kind = "measured" if identifier.startswith("measured_") else "prediction"
        if not frozen_result(request, f"/research/results/{kind}/{identifier}"):
            continue
        if kind == "measured":
            row, _ = request.app.state.measured.store.get(identifier)
            row.update(message="公开冻结实测结果", error_message=None, summary=None)
        else:
            row = container.store.get(identifier).model_dump(mode="json")
            row.update(warnings=[], error_code=None, error_message=None)
        rows.append((kind, row))
    return rows


def public_listing(request, path):
    try:
        limit, offset = (
            int(request.query_params.get("limit", "20")),
            int(request.query_params.get("offset", "0")),
        )
        if not 1 <= limit <= 100 or not 0 <= offset <= 1_000_000:
            raise ValueError
    except ValueError:
        return JSONResponse({"detail": "Invalid pagination"}, status_code=422)
    term = request.query_params.get("q", "").strip().casefold()
    status = request.query_params.get("status", "all")
    items = []
    for kind, row in public_records(request):
        if status not in {"all", "completed"}:
            continue
        if path == "/measured/analyses":
            if kind == "measured":
                items.append(row)
            continue
        if kind != "prediction":
            continue
        if (
            term
            and term
            not in " ".join(
                (row["run_id"], row["request"]["cell_line"], row["request"]["perturbation"])
            ).casefold()
        ):
            continue
        if path == "/runs":
            items.append(row)
        else:
            items.append(
                {
                    "id": row["run_id"],
                    "source": "online",
                    "status": row["status"],
                    "title": f"{row['request']['cell_line']} / {row['request']['perturbation']} 扰动实验",
                    "subtitle": "公开冻结模型结果",
                    "created_at": row["created_at"],
                    "run": row,
                }
            )
    items.sort(key=lambda item: item["created_at"], reverse=True)
    return JSONResponse(
        {"items": items[offset : offset + limit], "total": len(items), "limit": limit, "offset": offset},
        headers={"Cache-Control": "no-store"},
    )


def public_catalog(request, *, pair=False):
    """Read the pinned public metadata snapshot only, never private H5AD/registry probes."""
    from backend.app.services.perturbation_catalog import catalog_document

    document = catalog_document(request.app.state.container.settings.project_root)
    counts = {(row["cell_line"], row["perturbation"]): row["cell_count"] for row in document["counts"]}
    published = {}
    for kind, row in public_records(request):
        identity = row if kind == "measured" else row["request"]
        published.setdefault((identity["cell_line"], identity["perturbation"]), set()).add(kind)
    items = []
    for (cell, target), kinds in sorted(published.items()):
        count = counts.get((cell, target))
        # A sampled or privately imported matrix cannot stand in for a complete atlas count.
        items.append(
            {
                "cell_line": cell,
                "perturbation": target,
                "source_cell_count": count,
                "source_status": "measured" if count is not None else "unknown",
                "local_verified": False,
                "local_measured_cells": 0,
                "model_supported": "prediction" in kinds,
                "official_split": "unknown",
                "training_exclusion_verified": False,
                "generalization_verified": False,
                "recommended_action": "check_source",
            }
        )
    query = request.query_params
    filtered = [
        row
        for row in items
        if (not query.get("cell_line") or row["cell_line"] == query["cell_line"])
        and query.get("query", "").upper() in row["perturbation"].upper()
        and (query.get("availability", "all") == "all" or row["source_status"] == query["availability"])
        and (
            query.get("model_supported") is None
            or row["model_supported"] == (query["model_supported"].lower() == "true")
        )
    ]
    if pair:
        row = next(
            (row for row in filtered if row["perturbation"] == query.get("perturbation", "").upper()), None
        )
        return JSONResponse(
            row if row else {"detail": "Public pair not registered"},
            status_code=200 if row else 404,
            headers={"Cache-Control": "no-store"},
        )
    try:
        limit, offset = int(query.get("limit", "50")), int(query.get("offset", "0"))
        if not 1 <= limit <= 200 or offset < 0:
            raise ValueError
    except ValueError:
        return JSONResponse({"detail": "Invalid pagination"}, status_code=422)
    measured = sum(row["source_status"] == "measured" for row in items)
    return JSONResponse(
        {
            "items": filtered[offset : offset + limit],
            "total": len(filtered),
            "source_verified": document["source_verified"],
            "source": {
                **document["source"],
                "scope": "allowlisted_frozen_results",
                "manifest_sha256": document.get("manifest_sha256"),
            },
            "summary": {
                "pairs": len(items),
                "measured_pairs": measured,
                "model_supported_pairs": sum(row["model_supported"] for row in items),
                "model_supported_unmeasured_pairs": None,
                "unknown_pairs": len(items) - measured,
                "local_verified_pairs": 0,
                "contexts": [
                    {
                        "cell_line": cell,
                        "source_total_cells": None,
                        "measured_pairs": sum(
                            row["cell_line"] == cell and row["source_status"] == "measured" for row in items
                        ),
                        "model_supported_pairs": sum(
                            row["cell_line"] == cell and row["model_supported"] for row in items
                        ),
                        "model_supported_unmeasured_pairs": None,
                    }
                    for cell in sorted({row["cell_line"] for row in items})
                ],
            },
        },
        headers={"Cache-Control": "no-store"},
    )


class WorkspaceAccessMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings):
        super().__init__(app)
        self.settings = settings

    async def dispatch(self, request, call_next):
        settings = self.settings
        path = request.url.path
        if settings.deployment_mode == "local" and local_request(request) and not local_host_allowed(request):
            return JSONResponse(
                {"detail": {"code": "LOCAL_HOST_REJECTED", "message": "请使用 localhost 或本机回环地址访问"}},
                status_code=400,
                headers={"Cache-Control": "no-store"},
            )
        if not path.startswith(settings.api_prefix + "/"):
            return await call_next(request)
        relative = path[len(settings.api_prefix) :]
        if settings.deployment_mode == "public" and request.method not in {"GET", "HEAD"}:
            return JSONResponse({"detail": {"code": "PUBLIC_READ_ONLY"}}, status_code=403)
        if relative in {"/health", "/ready", "/auth/session"}:
            if request.method not in {"GET", "HEAD", "OPTIONS"} and not same_origin_request(request):
                return JSONResponse({"detail": "Cross-origin workspace mutation denied"}, status_code=403)
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            return response
        if settings.deployment_mode == "public":
            if relative in {"/runs", "/experiments", "/measured/analyses"}:
                return public_listing(request, relative)
            if relative in {"/data-catalog", "/data-catalog/pair"}:
                return public_catalog(request, pair=relative.endswith("/pair"))
            if request.method not in {"GET", "HEAD"} or not public_path(relative, settings):
                return JSONResponse(
                    {"detail": {"code": "PUBLIC_READ_ONLY", "message": "公开部署仅开放已登记的冻结案例"}},
                    status_code=403,
                )
            if not frozen_result(request, relative):
                return JSONResponse({"detail": {"code": "PUBLIC_RESULT_NOT_FROZEN"}}, status_code=404)
        elif not authenticated(request, settings):
            configured = settings.deployment_mode == "local" or bool(settings.workspace_token)
            return JSONResponse(
                {
                    "detail": {
                        "code": "WORKSPACE_AUTH_REQUIRED" if configured else "WORKSPACE_NOT_CONFIGURED",
                        "message": "请登录私有研究工作空间" if configured else "请配置工作空间访问令牌",
                    }
                },
                status_code=401 if configured else 503,
                headers={"Cache-Control": "no-store"},
            )
        elif request.method not in {"GET", "HEAD", "OPTIONS"}:
            # Cookie clients require same-origin writes; bearer clients may omit Origin.
            if not same_origin_request(request):
                return JSONResponse({"detail": "Cross-origin workspace mutation denied"}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        if settings.deployment_mode == "public" and "application/json" in response.headers.get(
            "content-type", ""
        ):
            from backend.app.services.research_results import sanitize

            # Legacy detail readers may carry input locations in summary/provenance.
            # Apply the same public projection as the unified result adapter.
            body_iterator = getattr(response, "body_iterator", None)
            body = (
                b"".join([part async for part in body_iterator])
                if isinstance(body_iterator, AsyncIterable)
                else bytes(response.body)
            )
            payload = sanitize(json.loads(body), public=True)
            headers = {
                key: value for key, value in response.headers.items() if key.lower() != "content-length"
            }
            return JSONResponse(
                payload, status_code=response.status_code, headers=headers, background=response.background
            )
        return response


class Login(BaseModel):
    token: str = Field(min_length=1, max_length=1024)


@router.get("/session")
def session_status(request: Request):
    settings = request.app.state.container.settings
    return {
        "mode": settings.deployment_mode,
        "authenticated": authenticated(request, settings),
        "configured": settings.deployment_mode != "private" or bool(settings.workspace_token),
        "read_only": settings.deployment_mode == "public",
        "public_result_ids": sorted(public_ids(settings)),
    }


@router.post("/session")
def login(body: Login, request: Request):
    settings = request.app.state.container.settings
    if not same_origin_request(request):
        raise HTTPException(403, "Cross-origin login denied")
    if settings.deployment_mode != "private" or not settings.workspace_token:
        raise HTTPException(403, "Private workspace login is unavailable")
    if not hmac.compare_digest(body.token.encode(), settings.workspace_token.encode()):
        raise HTTPException(401, "Invalid workspace token")
    response = JSONResponse({"authenticated": True, "mode": "private"}, headers={"Cache-Control": "no-store"})
    response.set_cookie(
        COOKIE,
        session_value(settings, int(time.time()) + 8 * 3600),
        max_age=8 * 3600,
        httponly=True,
        secure=settings.session_secure_cookie,
        samesite="strict",
        path="/",
    )
    return response


@router.delete("/session")
def logout():
    response = JSONResponse({"authenticated": False}, headers={"Cache-Control": "no-store"})
    response.delete_cookie(COOKIE, path="/")
    return response
