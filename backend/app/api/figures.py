"""Private figure workspaces; public sharing continues through frozen publications."""

from typing import Literal, cast

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from backend.app.api.research import HEADERS, Kind, translate
from backend.app.api.resources import same_origin
from backend.app.services.expression_atlas import ExpressionAtlasSpec, expression_atlas
from backend.app.services.figure_workspace import (
    FORMATS,
    FigureSpec,
    FigureWorkspace,
    export_payload,
    export_report,
)

router = APIRouter(prefix="/figures", tags=["figures"])
Format = Literal["svg", "png", "pdf", "csv", "html", "zip"]


@router.get("/measured/{identifier}/expression-summary")
def expression_summary(identifier: str, request: Request):
    """Read and verify once, rather than repeating CSV/hash work for every page."""
    import json

    from backend.app.services.measured_results import read_table

    try:
        _, directory, summary, _ = FigureWorkspace(request.app.state.container).source("measured", identifier)
        frame = read_table(directory, "genes")[["gene", "control", "observed", "observed_delta"]]
        return JSONResponse(
            {
                "record_id": identifier,
                "total": len(frame),
                "units": summary.get("expression_units"),
                "items": json.loads(cast(str, frame.to_json(orient="records"))),
            },
            headers=HEADERS,
        )
    except (KeyError, ValueError, OSError, ImportError) as exc:
        raise translate(exc) from exc


def response(payload, format):
    return Response(
        export_payload(payload, format),
        media_type=FORMATS[format],
        headers={
            **HEADERS,
            "Content-Disposition": f'attachment; filename="celllens-{payload["spec"]["chart"]}.{format}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{kind}/{identifier}/context")
def context(kind: Kind, identifier: str, request: Request):
    try:
        return JSONResponse(
            FigureWorkspace(request.app.state.container).context(kind, identifier), headers=HEADERS
        )
    except (KeyError, ValueError, OSError, ImportError) as exc:
        raise translate(exc) from exc


@router.post("/{kind}/{identifier}/render")
def render(kind: Kind, identifier: str, body: FigureSpec, request: Request, format: Format = "svg"):
    same_origin(request)
    try:
        return response(FigureWorkspace(request.app.state.container).payload(kind, identifier, body), format)
    except (KeyError, ValueError, OSError, ImportError) as exc:
        raise translate(exc) from exc


@router.post("/{kind}/{identifier}/expression-atlas")
def atlas(kind: Kind, identifier: str, body: ExpressionAtlasSpec, request: Request):
    same_origin(request)
    try:
        return JSONResponse(
            expression_atlas(FigureWorkspace(request.app.state.container), kind, identifier, body),
            headers=HEADERS,
        )
    except (KeyError, ValueError, OSError, ImportError) as exc:
        raise translate(exc) from exc


@router.get("/{kind}/{identifier}/saved")
def saved(kind: Kind, identifier: str, request: Request):
    try:
        return JSONResponse(
            FigureWorkspace(request.app.state.container).saved(kind, identifier), headers=HEADERS
        )
    except (KeyError, ValueError, OSError, ImportError) as exc:
        raise translate(exc) from exc


@router.post("/{kind}/{identifier}/saved", status_code=201)
def save(kind: Kind, identifier: str, body: FigureSpec, request: Request):
    same_origin(request)
    try:
        return JSONResponse(
            FigureWorkspace(request.app.state.container).save(kind, identifier, body),
            status_code=201,
            headers=HEADERS,
        )
    except (KeyError, ValueError, OSError, ImportError) as exc:
        raise translate(exc) from exc


@router.get("/{kind}/{identifier}/saved/{figure_id}/export")
def saved_export(kind: Kind, identifier: str, figure_id: str, request: Request, format: Format = "zip"):
    try:
        payload = FigureWorkspace(request.app.state.container).saved_payload(kind, identifier, figure_id)
        return response(payload, format)
    except (KeyError, ValueError, OSError, ImportError) as exc:
        raise translate(exc) from exc


@router.get("/{kind}/{identifier}/report")
def report_export(kind: Kind, identifier: str, request: Request, format: Literal["html", "zip"] = "html"):
    try:
        return Response(
            export_report(request.app.state.container, kind, identifier, format),
            media_type=FORMATS[format],
            headers={
                **HEADERS,
                "Content-Disposition": f'attachment; filename="celllens-report.{format}"',
                "X-Content-Type-Options": "nosniff",
            },
        )
    except (KeyError, ValueError, OSError, ImportError) as exc:
        raise translate(exc) from exc


@router.delete("/{kind}/{identifier}/saved/{figure_id}", status_code=204)
def remove(kind: Kind, identifier: str, figure_id: str, request: Request):
    same_origin(request)
    try:
        FigureWorkspace(request.app.state.container).remove(kind, identifier, figure_id)
        return Response(status_code=204, headers=HEADERS)
    except (KeyError, ValueError, OSError, ImportError) as exc:
        raise translate(exc) from exc
