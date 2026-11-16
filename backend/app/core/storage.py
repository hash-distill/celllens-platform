import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import Engine, and_, create_engine, exists, func, or_, select, text, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.errors import InvalidTransitionError, JobAlreadyClaimedError
from backend.app.db.models import (
    Base,
    RunArtifactModel,
    RunAttemptModel,
    RunCacheModel,
    RunEventModel,
    RunModel,
)
from backend.app.schemas import CreateRunRequest, RunRecord, RunStatus


@dataclass(frozen=True)
class RunAttempt:
    id: int
    run_id: str
    attempt_no: int
    worker_id: str
    lease_expires_at: datetime


@dataclass(frozen=True)
class RunEvent:
    from_status: str | None
    to_status: str
    stage_progress: int
    message: str | None


@dataclass(frozen=True)
class RunArtifact:
    kind: str
    relative_path: str
    sha256: str
    size_bytes: int
    mime_type: str


ALLOWED_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.QUEUED: {RunStatus.STATE_RUNNING, RunStatus.COMPLETED, RunStatus.FAILED},
    RunStatus.STATE_RUNNING: {RunStatus.ADAPTING, RunStatus.FAILED},
    RunStatus.ADAPTING: {
        RunStatus.METABOLIC_RUNNING,
        RunStatus.VALIDATING,
        RunStatus.COMPLETED,
        RunStatus.FAILED,
    },
    RunStatus.METABOLIC_RUNNING: {RunStatus.VALIDATING, RunStatus.COMPLETED, RunStatus.FAILED},
    RunStatus.VALIDATING: {RunStatus.COMPLETED, RunStatus.FAILED},
    RunStatus.COMPLETED: set(),
    RunStatus.FAILED: set(),
}


class RunStore:
    _local_named_locks: dict[str, threading.Lock] = {}
    _local_named_locks_guard = threading.Lock()

    def __init__(self, database_url: str, *, create_schema: bool = False):
        self.engine: Engine = create_engine(database_url, pool_pre_ping=True, future=True)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False, class_=Session)
        self._ownership = threading.local()
        if create_schema:
            Base.metadata.create_all(self.engine)

    def ping(self) -> bool:
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True

    @contextmanager
    def named_lock(self, name: str, *, timeout_seconds: int) -> Iterator[None]:
        """Hold a cross-process MySQL advisory lock on the same connection."""
        if self.engine.dialect.name == "mysql":
            with self.engine.connect() as connection:
                acquired = connection.execute(
                    text("SELECT GET_LOCK(:name, :timeout)"),
                    {"name": name, "timeout": timeout_seconds},
                ).scalar()
                if acquired != 1:
                    raise JobAlreadyClaimedError(f"Timed out acquiring shared resource lock {name}")
                try:
                    yield
                finally:
                    connection.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": name})
            return
        with self._local_named_locks_guard:
            lock = self._local_named_locks.setdefault(name, threading.Lock())
        if not lock.acquire(timeout=timeout_seconds):
            raise JobAlreadyClaimedError(f"Timed out acquiring local resource lock {name}")
        try:
            yield
        finally:
            lock.release()

    def create(self, run_id: str, request: CreateRunRequest, *, cache_key: str | None = None) -> RunRecord:
        now = datetime.now(UTC)
        with self.session_factory.begin() as session:
            session.add(
                RunModel(
                    run_id=run_id,
                    mode=request.mode,
                    cell_line=request.cell_line,
                    perturbation=request.perturbation,
                    n_cells=request.n_cells,
                    seed=request.seed,
                    status=RunStatus.QUEUED.value,
                    stage_progress=0,
                    request_json=request.model_dump(mode="json"),
                    warnings_json=[],
                    cache_key=cache_key,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add(
                RunEventModel(
                    run_id=run_id,
                    from_status=None,
                    to_status=RunStatus.QUEUED.value,
                    stage_progress=0,
                    message="run created",
                    created_at=now,
                )
            )
        return self.get(run_id)

    def get(self, run_id: str) -> RunRecord:
        with self.session_factory() as session:
            model = session.get(RunModel, run_id)
            if model is None:
                raise KeyError(run_id)
            return self._decode(model)

    def list_runs(
        self, *, limit: int, offset: int, query: str = "", status: str = "all", mode: str | None = None
    ) -> tuple[list[RunRecord], int]:
        statement = select(RunModel)
        if query.strip():
            term = query.strip()
            statement = statement.where(
                or_(
                    RunModel.run_id.icontains(term, autoescape=True),
                    RunModel.perturbation.icontains(term, autoescape=True),
                    RunModel.cell_line.icontains(term, autoescape=True),
                )
            )
        if status == "active":
            statement = statement.where(RunModel.status.notin_(["completed", "failed"]))
        elif status != "all":
            statement = statement.where(RunModel.status == status)
        if mode:
            statement = statement.where(RunModel.mode == mode)
        with self.session_factory() as session:
            total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
            rows = session.scalars(
                statement.order_by(RunModel.created_at.desc(), RunModel.run_id.desc())
                .limit(limit)
                .offset(offset)
            ).all()
            return [self._decode(row) for row in rows], int(total)

    def transition(
        self,
        run_id: str,
        status: RunStatus,
        progress: int,
        *,
        warnings: list[str] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        message: str | None = None,
    ) -> RunRecord:
        with self.session_factory.begin() as session:
            self._lock_owned(session, run_id)
            model = session.scalar(select(RunModel).where(RunModel.run_id == run_id).with_for_update())
            if model is None:
                raise KeyError(run_id)
            current = RunStatus(model.status)
            if status != current and status not in ALLOWED_TRANSITIONS[current]:
                raise InvalidTransitionError(f"Cannot transition {current.value} -> {status.value}")
            if progress < model.stage_progress:
                raise InvalidTransitionError(
                    f"Progress cannot decrease from {model.stage_progress} to {progress}"
                )
            now = datetime.now(UTC)
            model.status = status.value
            model.stage_progress = progress
            model.updated_at = now
            if warnings is not None:
                model.warnings_json = list(warnings)
            model.error_code = error_code
            model.error_message = error_message
            if status != current:
                session.add(
                    RunEventModel(
                        run_id=run_id,
                        from_status=current.value,
                        to_status=status.value,
                        stage_progress=progress,
                        message=message,
                        created_at=now,
                    )
                )
        return self.get(run_id)

    def start_attempt(self, run_id: str, *, worker_id: str, lease_seconds: int) -> RunAttempt:
        now = datetime.now(UTC)
        lease = now + timedelta(seconds=lease_seconds)
        with self.session_factory.begin() as session:
            live_attempt = exists().where(
                RunAttemptModel.run_id == RunModel.run_id,
                RunAttemptModel.status == "running",
                RunAttemptModel.lease_expires_at >= now,
            )
            claimed = session.execute(
                update(RunModel)
                .where(
                    RunModel.run_id == run_id,
                    RunModel.status.notin_(["completed", "failed"]),
                    ~live_attempt,
                )
                .values(updated_at=now)
            )
            if cast(CursorResult, claimed).rowcount != 1:
                if session.get(RunModel, run_id) is None:
                    raise KeyError(run_id)
                raise JobAlreadyClaimedError(f"Run {run_id} is terminal or already owned")
            run = session.scalar(select(RunModel).where(RunModel.run_id == run_id).with_for_update())
            if run is None:
                raise KeyError(run_id)
            if RunStatus(run.status) in {RunStatus.COMPLETED, RunStatus.FAILED}:
                raise InvalidTransitionError(f"Cannot start an attempt for terminal run {run_id}")
            live = session.scalar(
                select(RunAttemptModel.id).where(
                    RunAttemptModel.run_id == run_id,
                    RunAttemptModel.status == "running",
                    RunAttemptModel.lease_expires_at >= now,
                )
            )
            if live is not None:
                raise JobAlreadyClaimedError(f"Run {run_id} already has a live worker lease")
            session.execute(
                update(RunAttemptModel)
                .where(
                    RunAttemptModel.run_id == run_id,
                    RunAttemptModel.status == "running",
                )
                .values(status="abandoned", finished_at=now)
            )
            maximum = session.scalar(
                select(func.max(RunAttemptModel.attempt_no)).where(RunAttemptModel.run_id == run_id)
            )
            model = RunAttemptModel(
                run_id=run_id,
                attempt_no=(maximum or 0) + 1,
                status="running",
                worker_id=worker_id,
                lease_expires_at=lease,
                heartbeat_at=now,
                started_at=now,
            )
            session.add(model)
            session.flush()
            result = RunAttempt(model.id, run_id, model.attempt_no, worker_id, lease)
        owned = getattr(self._ownership, "attempts", {})
        owned[run_id] = result.id
        self._ownership.attempts = owned
        return result

    def _lock_owned(self, session, run_id: str) -> None:
        """A conditional UPDATE provides serialization on SQLite as well as MySQL."""
        attempt_id = getattr(self._ownership, "attempts", {}).get(run_id)
        conditions = [RunModel.run_id == run_id]
        if attempt_id is not None:
            conditions.append(
                exists().where(
                    RunAttemptModel.id == attempt_id,
                    RunAttemptModel.run_id == RunModel.run_id,
                    RunAttemptModel.status == "running",
                    RunAttemptModel.lease_expires_at >= datetime.now(UTC),
                )
            )
        result = session.execute(update(RunModel).where(*conditions).values(updated_at=RunModel.updated_at))
        if result.rowcount != 1:
            raise JobAlreadyClaimedError(f"Worker ownership lost for {run_id}")

    def publish_attempt(self, run_id: str, partial, final) -> None:
        if run_id not in getattr(self._ownership, "attempts", {}):
            raise JobAlreadyClaimedError("Publishing requires a claimed attempt in this worker thread")
        with self.session_factory.begin() as session:
            self._lock_owned(session, run_id)
            if final.exists():
                raise FileExistsError(f"Immutable run directory already exists: {final}")
            partial.replace(final)

    def heartbeat(self, attempt_id: int, lease_seconds: int) -> None:
        now = datetime.now(UTC)
        with self.session_factory.begin() as session:
            result = session.execute(
                update(RunAttemptModel)
                .where(
                    RunAttemptModel.id == attempt_id,
                    RunAttemptModel.status == "running",
                    RunAttemptModel.lease_expires_at >= now,
                )
                .values(heartbeat_at=now, lease_expires_at=now + timedelta(seconds=lease_seconds))
            )
            if cast(CursorResult, result).rowcount != 1:
                raise JobAlreadyClaimedError(f"Attempt lease lost: {attempt_id}")

    def finish_attempt(self, attempt_id: int, *, succeeded: bool, error_code: str | None = None) -> None:
        with self.session_factory.begin() as session:
            session.execute(
                update(RunAttemptModel)
                .where(
                    RunAttemptModel.id == attempt_id,
                    RunAttemptModel.status == "running",
                    RunAttemptModel.lease_expires_at >= datetime.now(UTC),
                )
                .values(
                    status="succeeded" if succeeded else "failed",
                    error_code=error_code,
                    finished_at=datetime.now(UTC),
                )
            )

    def force_attempt_lease(self, attempt_id: int, value: datetime) -> None:
        """Testing and administrative recovery hook."""
        with self.session_factory.begin() as session:
            model = session.get(RunAttemptModel, attempt_id)
            if model is None:
                raise KeyError(attempt_id)
            model.lease_expires_at = value

    def cancel(self, run_id: str) -> RunRecord:
        now = datetime.now(UTC)
        with self.session_factory.begin() as session:
            # Serialize cancellation with publication, without assuming API ownership.
            session.execute(
                update(RunModel).where(RunModel.run_id == run_id).values(updated_at=RunModel.updated_at)
            )
            row = session.get(RunModel, run_id)
            if row is None:
                raise KeyError(run_id)
            if row.status in {"completed", "failed"}:
                return self._decode(row)
            previous = row.status
            row.status, row.error_code = "failed", "RUN_CANCELLED"
            row.error_message, row.updated_at = "用户取消了预测任务", now
            session.execute(
                update(RunAttemptModel)
                .where(RunAttemptModel.run_id == run_id, RunAttemptModel.status == "running")
                .values(status="cancelled", finished_at=now, error_code="RUN_CANCELLED")
            )
            session.add(
                RunEventModel(
                    run_id=run_id,
                    from_status=previous,
                    to_status="failed",
                    stage_progress=row.stage_progress,
                    message="user cancelled",
                    created_at=now,
                )
            )
        return self.get(run_id)

    def attempts(self, run_id: str) -> list[dict]:
        with self.session_factory() as session:
            rows = session.scalars(
                select(RunAttemptModel)
                .where(RunAttemptModel.run_id == run_id)
                .order_by(RunAttemptModel.attempt_no)
            )
            return [
                {
                    "attempt_no": row.attempt_no,
                    "status": row.status,
                    "heartbeat_at": row.heartbeat_at.isoformat(),
                    "lease_expires_at": row.lease_expires_at.isoformat(),
                    "started_at": row.started_at.isoformat(),
                    "finished_at": row.finished_at.isoformat() if row.finished_at else None,
                    "error_code": row.error_code,
                }
                for row in rows
            ]

    def list_recoverable_run_ids(self) -> list[str]:
        now = datetime.now(UTC)
        active = {
            RunStatus.STATE_RUNNING.value,
            RunStatus.ADAPTING.value,
            RunStatus.METABOLIC_RUNNING.value,
            RunStatus.VALIDATING.value,
        }
        live_attempt = exists().where(
            and_(
                RunAttemptModel.run_id == RunModel.run_id,
                RunAttemptModel.status == "running",
                RunAttemptModel.lease_expires_at >= now,
            )
        )
        statement = select(RunModel.run_id).where(
            and_(
                ~live_attempt,
                or_(RunModel.status == RunStatus.QUEUED.value, RunModel.status.in_(active)),
            )
        )
        with self.session_factory() as session:
            return list(session.scalars(statement))

    def prepare_recovery(self, run_id: str) -> RunRecord:
        """Reset an abandoned active run so a fresh leased attempt can replay it."""
        now = datetime.now(UTC)
        with self.session_factory.begin() as session:
            live_attempt = exists().where(
                RunAttemptModel.run_id == RunModel.run_id,
                RunAttemptModel.status == "running",
                RunAttemptModel.lease_expires_at >= now,
            )
            guard = session.execute(
                update(RunModel)
                .where(
                    RunModel.run_id == run_id,
                    ~live_attempt,
                )
                .values(updated_at=RunModel.updated_at)
            )
            if cast(CursorResult, guard).rowcount != 1:
                raise JobAlreadyClaimedError(f"Run {run_id} still has a live worker lease")
            model = session.scalar(select(RunModel).where(RunModel.run_id == run_id).with_for_update())
            if model is None:
                raise KeyError(run_id)
            current = RunStatus(model.status)
            if current == RunStatus.QUEUED:
                return self._decode(model)
            if current in {RunStatus.COMPLETED, RunStatus.FAILED}:
                raise InvalidTransitionError(f"Cannot recover terminal run {run_id}")
            live = session.scalar(
                select(RunAttemptModel.id).where(
                    RunAttemptModel.run_id == run_id,
                    RunAttemptModel.status == "running",
                    RunAttemptModel.lease_expires_at >= now,
                )
            )
            if live is not None:
                raise JobAlreadyClaimedError(f"Run {run_id} still has a live worker lease")
            session.query(RunAttemptModel).filter(
                RunAttemptModel.run_id == run_id,
                RunAttemptModel.status == "running",
            ).update({"status": "abandoned", "finished_at": now})
            model.status = RunStatus.QUEUED.value
            model.stage_progress = 0
            model.updated_at = now
            session.add(
                RunEventModel(
                    run_id=run_id,
                    from_status=current.value,
                    to_status=RunStatus.QUEUED.value,
                    stage_progress=0,
                    message="expired worker lease recovered",
                    created_at=now,
                )
            )
        return self.get(run_id)

    def events(self, run_id: str) -> list[RunEvent]:
        statement = select(RunEventModel).where(RunEventModel.run_id == run_id).order_by(RunEventModel.id)
        with self.session_factory() as session:
            return [
                RunEvent(row.from_status, row.to_status, row.stage_progress, row.message)
                for row in session.scalars(statement)
            ]

    def register_artifact(
        self,
        run_id: str,
        kind: str,
        relative_path: str,
        sha256: str,
        size_bytes: int,
        mime_type: str,
    ) -> None:
        with self.session_factory.begin() as session:
            self._lock_owned(session, run_id)
            existing = session.scalar(
                select(RunArtifactModel).where(
                    RunArtifactModel.run_id == run_id,
                    RunArtifactModel.kind == kind,
                )
            )
            if existing:
                if (existing.relative_path, existing.sha256, existing.size_bytes) != (
                    relative_path,
                    sha256,
                    size_bytes,
                ):
                    raise ValueError("An immutable registered artifact cannot be replaced")
                return
            session.add(
                RunArtifactModel(
                    run_id=run_id,
                    kind=kind,
                    relative_path=relative_path,
                    sha256=sha256,
                    size_bytes=size_bytes,
                    mime_type=mime_type,
                    created_at=datetime.now(UTC),
                )
            )

    def artifacts(self, run_id: str) -> list[RunArtifact]:
        statement = select(RunArtifactModel).where(RunArtifactModel.run_id == run_id)
        with self.session_factory() as session:
            return [
                RunArtifact(row.kind, row.relative_path, row.sha256, row.size_bytes, row.mime_type)
                for row in session.scalars(statement)
            ]

    def put_cache(self, cache_key: str, run_id: str) -> None:
        with self.session_factory.begin() as session:
            session.merge(RunCacheModel(cache_key=cache_key, run_id=run_id, created_at=datetime.now(UTC)))

    def get_cached_run(self, cache_key: str) -> str | None:
        statement = (
            select(RunCacheModel.run_id)
            .join(RunModel, RunModel.run_id == RunCacheModel.run_id)
            .where(RunCacheModel.cache_key == cache_key, RunModel.status == RunStatus.COMPLETED.value)
        )
        with self.session_factory() as session:
            return session.scalar(statement)

    def cache_key(self, run_id: str) -> str | None:
        with self.session_factory() as session:
            value = session.scalar(select(RunModel.cache_key).where(RunModel.run_id == run_id))
        return value

    @staticmethod
    def _decode(model: RunModel) -> RunRecord:
        return RunRecord(
            run_id=model.run_id,
            status=RunStatus(model.status),
            stage_progress=model.stage_progress,
            request=CreateRunRequest.model_validate(model.request_json),
            created_at=model.created_at,
            updated_at=model.updated_at,
            warnings=list(model.warnings_json or []),
            error_code=model.error_code,
            error_message=model.error_message,
        )
