"""Searchable, paginated history of online perturbation experiments."""

from datetime import UTC
from typing import Literal

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, or_, select

from backend.app.db.models import RunModel

router = APIRouter(tags=["experiments"])


@router.get("/experiments")
def experiments(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=1_000_000),
    q: str = Query("", max_length=128),
    status: Literal["all", "active", "completed", "failed"] = "all",
    source: Literal["online"] | None = None,
) -> dict:
    statement = select(RunModel).where(RunModel.mode == "online")
    if status == "active":
        statement = statement.where(RunModel.status.notin_(["completed", "failed"]))
    elif status != "all":
        statement = statement.where(RunModel.status == status)
    if q.strip():
        term = q.strip()
        statement = statement.where(
            or_(
                RunModel.run_id.icontains(term, autoescape=True),
                RunModel.cell_line.icontains(term, autoescape=True),
                RunModel.perturbation.icontains(term, autoescape=True),
            )
        )
    store = request.app.state.container.store
    with store.session_factory() as session:
        total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        rows = session.scalars(
            statement.order_by(RunModel.created_at.desc(), RunModel.run_id.desc()).limit(limit).offset(offset)
        ).all()
        items = []
        for row in rows:
            record = store.get(row.run_id).model_dump(mode="json")
            items.append(
                {
                    "id": row.run_id,
                    "source": "online",
                    "status": row.status,
                    "title": f"{row.cell_line} / {row.perturbation} 扰动实验",
                    "subtitle": f"请求 {record['request']['n_cells']} 个预测细胞",
                    "created_at": row.created_at.replace(tzinfo=UTC).isoformat(),
                    "run": record,
                }
            )
    return {"items": items, "total": total, "limit": limit, "offset": offset}
