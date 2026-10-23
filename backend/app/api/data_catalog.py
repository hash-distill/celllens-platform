"""Read-only public-source coverage endpoints; GET never starts extraction or inference."""

import csv
import io
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from backend.app.services.perturbation_catalog import pair_detail, query_pairs

router = APIRouter(prefix="/data-catalog", tags=["data-catalog"])
Availability = Literal["all", "measured", "missing", "unknown"]


@router.get("")
def catalog(
    request: Request,
    cell_line: str | None = None,
    query: str = Query("", max_length=64),
    availability: Availability = "all",
    model_supported: bool | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    try:
        return query_pairs(
            request.app.state.container,
            cell_line=cell_line,
            query=query,
            availability=availability,
            model_supported=model_supported,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc


@router.get("/pair")
def pair(request: Request, cell_line: str, perturbation: str) -> dict:
    try:
        return pair_detail(request.app.state.container, cell_line, perturbation)
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc


@router.get("/download.csv")
def download(
    request: Request,
    cell_line: str | None = None,
    query: str = Query("", max_length=64),
    availability: Availability = "all",
    model_supported: bool | None = None,
) -> Response:
    try:
        payload = query_pairs(
            request.app.state.container,
            cell_line=cell_line,
            query=query,
            availability=availability,
            model_supported=model_supported,
            limit=100000,
        )
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    fields = [
        "cell_line",
        "perturbation",
        "source_cell_count",
        "source_status",
        "local_verified",
        "local_measured_cells",
        "model_supported",
        "official_split",
        "training_exclusion_verified",
        "generalization_verified",
        "recommended_action",
        "source_repo",
        "source_revision",
        "source_verified",
        "source_manifest_sha256",
    ]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fields)
    writer.writeheader()
    for row in payload["items"]:
        writer.writerow(
            {
                **row,
                "source_repo": payload["source"]["repo"],
                "source_revision": payload["source"]["revision"],
                "source_verified": payload["source_verified"],
                "source_manifest_sha256": payload["source"].get("manifest_sha256"),
            }
        )
    return Response(
        "\ufeff" + stream.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="celllens-data-catalog.csv"',
            "Cache-Control": "no-store",
        },
    )
