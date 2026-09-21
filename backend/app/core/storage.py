import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, and_, create_engine, exists, func, or_, select, text
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
        return result

    def heartbeat(self, attempt_id: int, lease_seconds: int) -> None:
        now = datetime.now(UTC)
        with self.session_factory.begin() as session:
            model = session.get(RunAttemptModel, attempt_id)
            if model is None:
                raise KeyError(attempt_id)
            model.heartbeat_at = now
            model.lease_expires_at = now + timedelta(seconds=lease_seconds)

    def finish_attempt(self, attempt_id: int, *, succeeded: bool, error_code: str | None = None) -> None:
        with self.session_factory.begin() as session:
            model = session.get(RunAttemptModel, attempt_id)
            if model is None:
                raise KeyError(attempt_id)
            model.status = "succeeded" if succeeded else "failed"
            model.error_code = error_code
            model.finished_at = datetime.now(UTC)

    def force_attempt_lease(self, attempt_id: int, value: datetime) -> None:
        """Testing and administrative recovery hook."""
        with self.session_factory.begin() as session:
            model = session.get(RunAttemptModel, attempt_id)
            if model is None:
                raise KeyError(attempt_id)
            model.lease_expires_at = value

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
