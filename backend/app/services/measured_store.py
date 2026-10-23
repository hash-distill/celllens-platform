"""Durable measured history, independent of predictive run states."""

from datetime import UTC, datetime

from sqlalchemy import func, select, update

from backend.app.db.models import MeasuredAnalysisModel as Model

ACTIVE = {"queued", "preparing", "analysing"}


def document(row: Model) -> dict:
    return {
        "id": row.id,
        "cell_line": row.cell_line,
        "perturbation": row.perturbation,
        "max_cells": row.max_cells,
        "seed": row.seed,
        "status": row.status,
        "progress": row.progress,
        "message": row.message,
        "error_message": row.error_message,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "source_kind": "measured",
        "summary": None,
    }


class MeasuredStore:
    def __init__(self, session_factory):
        self.sessions = session_factory

    def create(self, request: dict) -> dict:
        now = datetime.now(UTC)
        with self.sessions.begin() as session:
            row = Model(
                id=request["id"],
                cell_line=request["cell_line"],
                perturbation=request["perturbation"],
                max_cells=request["max_cells"],
                seed=request["seed"],
                status="queued",
                progress=0,
                message="实测分析已排队",
                request_json=request,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            return document(row)

    def get(self, identifier: str) -> tuple[dict, str | None]:
        with self.sessions() as session:
            row = session.get(Model, identifier)
            if row is None:
                raise KeyError(identifier)
            return document(row), row.manifest_sha256

    def list(self, limit: int = 20, offset: int = 0) -> dict:
        with self.sessions() as session:
            total = session.scalar(select(func.count()).select_from(Model))
            rows = session.scalars(
                select(Model).order_by(Model.created_at.desc()).limit(limit).offset(offset)
            )
            return {
                "items": [document(row) for row in rows],
                "total": total,
                "limit": limit,
                "offset": offset,
            }

    def update(self, identifier: str, **values) -> None:
        with self.sessions.begin() as session:
            session.execute(
                update(Model).where(Model.id == identifier).values(updated_at=datetime.now(UTC), **values)
            )

    def interrupt_active(self) -> None:
        with self.sessions.begin() as session:
            session.execute(
                update(Model)
                .where(Model.status.in_(ACTIVE))
                .values(
                    status="interrupted",
                    message="服务重启，原实测分析已中断；可创建新分析重试",
                    updated_at=datetime.now(UTC),
                )
            )
