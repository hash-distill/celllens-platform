"""Public catalog queries and private, bounded comparison submissions."""

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.app.api.resources import same_origin
from backend.app.services.dataset_registry import list_conditions, list_datasets

router = APIRouter(prefix="/datasets", tags=["datasets"])
HEADERS = {"Cache-Control": "no-store"}


class DatasetAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    condition_id: str = Field(min_length=1, max_length=128)
    max_cells: int = Field(256, ge=1, le=4096)
    seed: int = Field(42, ge=0, le=2147483647)


@router.get("")
def datasets(request: Request):
    return JSONResponse(list_datasets(request.app.state.container.settings.project_root), headers=HEADERS)


@router.get("/{dataset_id}/conditions")
def conditions(
    dataset_id: str,
    request: Request,
    query: str = Query("", max_length=200),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    try:
        result = list_conditions(
            request.app.state.container.settings.project_root, dataset_id, query, limit, offset
        )
    except KeyError as exc:
        raise HTTPException(404, detail="未登记的数据集") from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(409, detail=str(exc)) from exc
    return JSONResponse(result, headers=HEADERS)


@router.post("/{dataset_id}/analyses", status_code=202)
async def create(dataset_id: str, body: DatasetAnalysisRequest, request: Request):
    same_origin(request)
    try:
        row = await request.app.state.measured.start({"dataset_id": dataset_id, **body.model_dump()})
    except KeyError as exc:
        raise HTTPException(404, detail="未登记的数据集") from exc
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    except (RuntimeError, OSError) as exc:
        raise HTTPException(409, detail=str(exc)) from exc
    return JSONResponse(row, status_code=202, headers=HEADERS)
