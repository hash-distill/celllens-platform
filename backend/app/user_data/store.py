import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from backend.app.core.errors import ScientificContractError
from backend.app.core.storage import RunStore
from backend.app.user_data.models import DatasetModel, UserAnalysisModel


def now() -> datetime:
    # Naive UTC is portable between MySQL and SQLite; API dates explicitly carry Z.
    return datetime.now(UTC).replace(tzinfo=None)


def iso(value: datetime) -> str:
    return value.isoformat() + "Z"


def public_dataset(row: DatasetModel) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "filename": row.filename,
        "sha256": row.sha256,
        "size_bytes": row.size_bytes,
        "metadata": row.metadata_json,
        "summary": row.summary_json,
        "archived": row.archived,
        "created_at": iso(row.created_at),
    }


def public_analysis(row: UserAnalysisModel) -> dict[str, Any]:
    return {
        "id": row.id,
        "dataset_id": row.dataset_id,
        "name": row.request_json.get("name", row.kind),
        "kind": row.kind,
        "status": row.status,
        "request": row.request_json,
        "artifacts": row.artifacts_json,
        "error_message": row.error_message,
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }


class UserDataStore:
    def __init__(self, run_store: RunStore):
        self.runtime = run_store
        self.sessions = run_store.session_factory

    def dataset(self, dataset_id: str, owner_id: str | None) -> dict[str, Any] | None:
        with self.sessions() as session:
            row = session.scalar(
                select(DatasetModel).where(DatasetModel.id == dataset_id, DatasetModel.owner_id == owner_id)
            )
            return public_dataset(row) if row else None

    def datasets(self, owner_id: str | None, limit: int, offset: int, q: str = "") -> dict[str, Any]:
        with self.sessions() as session:
            query = select(DatasetModel).where(DatasetModel.owner_id == owner_id)
            if q.strip():
                query = query.where(DatasetModel.name.contains(q.strip(), autoescape=True))
            total = session.scalar(select(func.count()).select_from(query.subquery()))
            rows = session.scalars(query.order_by(DatasetModel.created_at.desc()).limit(limit).offset(offset))
            return {"items": [public_dataset(row) for row in rows], "total": total}

    def used_bytes(self, owner_id: str | None) -> int:
        with self.sessions() as session:
            return int(session.scalar(select(func.coalesce(func.sum(DatasetModel.size_bytes), 0))) or 0)

    def add_dataset(
        self,
        *,
        owner_id: str | None,
        dataset_id: str,
        metadata: dict,
        summary: dict,
        sha256: str,
        size_bytes: int,
        filename: str,
    ) -> dict[str, Any]:
        row = DatasetModel(
            id=dataset_id,
            owner_id=owner_id,
            name=metadata["name"],
            filename=filename,
            sha256=sha256,
            size_bytes=size_bytes,
            metadata_json=metadata,
            summary_json=summary,
            archived=False,
            created_at=now(),
        )
        with self.sessions.begin() as session:
            session.add(row)
        return public_dataset(row)

    def archive(self, dataset_id: str, owner_id: str | None) -> None:
        with self.sessions.begin() as session:
            row = session.scalar(
                select(DatasetModel)
                .where(DatasetModel.id == dataset_id, DatasetModel.owner_id == owner_id)
                .with_for_update()
            )
            if row:
                row.archived = True

    def create_analysis(self, owner_id: str | None, request: dict) -> dict[str, Any]:
        with (
            self.runtime.named_lock("celllens:shared-analysis-submit", timeout_seconds=10),
            self.sessions.begin() as session,
        ):
            dataset = session.scalar(
                select(DatasetModel)
                .where(DatasetModel.id == request["dataset_id"], DatasetModel.owner_id == owner_id)
                .with_for_update()
            )
            if dataset is None or dataset.archived:
                raise ScientificContractError("数据集不存在或已归档")
            count = session.scalar(
                select(func.count())
                .select_from(UserAnalysisModel)
                .where(
                    UserAnalysisModel.owner_id == owner_id,
                    UserAnalysisModel.status.in_(["queued", "running"]),
                )
            )
            if count and count >= 3:
                raise ValueError("共享工作区最多同时保留 3 个待完成分析任务")
            row = UserAnalysisModel(
                id="ana_" + uuid.uuid4().hex,
                owner_id=owner_id,
                dataset_id=request["dataset_id"],
                kind=request["kind"],
                status="queued",
                request_json=request,
                artifacts_json={},
                created_at=now(),
                updated_at=now(),
            )
            session.add(row)
        return public_analysis(row)

    def analysis(self, analysis_id: str, owner_id: str | None) -> dict[str, Any] | None:
        with self.sessions() as session:
            row = session.scalar(
                select(UserAnalysisModel).where(
                    UserAnalysisModel.id == analysis_id, UserAnalysisModel.owner_id == owner_id
                )
            )
            return public_analysis(row) if row else None

    def analyses(
        self,
        owner_id: str | None,
        limit: int,
        offset: int,
        dataset_id: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        with self.sessions() as session:
            query = select(UserAnalysisModel).where(UserAnalysisModel.owner_id == owner_id)
            if dataset_id:
                query = query.where(UserAnalysisModel.dataset_id == dataset_id)
            if status:
                query = query.where(UserAnalysisModel.status == status)
            total = session.scalar(select(func.count()).select_from(query.subquery()))
            rows = session.scalars(
                query.order_by(UserAnalysisModel.created_at.desc()).limit(limit).offset(offset)
            )
            return {"items": [public_analysis(row) for row in rows], "total": total}

    def next_job(self) -> tuple[dict[str, Any], dict[str, Any]] | None:
        # Caller holds the cross-process worker lock, including execution and completion.
        with self.sessions.begin() as session:
            row = session.scalar(
                select(UserAnalysisModel)
                .where(
                    UserAnalysisModel.owner_id.is_(None), UserAnalysisModel.status.in_(["queued", "running"])
                )
                .order_by(UserAnalysisModel.created_at)
                .limit(1)
            )
            if row is None:
                return None
            dataset = session.get(DatasetModel, row.dataset_id)
            assert dataset is not None
            row.status = "running"
            row.updated_at = now()
            return public_analysis(row), public_dataset(dataset)

    def finish(self, analysis_id: str, *, artifacts: dict | None = None, error: str | None = None) -> None:
        with self.sessions.begin() as session:
            row = session.get(UserAnalysisModel, analysis_id)
            assert row is not None
            row.status = "failed" if error else "completed"
            row.error_message = error
            row.artifacts_json = artifacts or {}
            row.updated_at = now()
