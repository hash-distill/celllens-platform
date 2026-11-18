"""Durable measured history, independent of predictive run states."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, or_, select, update

from backend.app.db.models import MeasuredAnalysisModel as Model
from backend.app.db.models import MeasuredAttemptModel as Attempt

ACTIVE = {"queued", "preparing", "analysing"}


def document(row: Model) -> dict:
    request = row.request_json or {}
    source = request.get("source") or {}
    identity = {
        key: source[key]
        for key in ("kind", "import_id", "source_sha256", "repo", "revision", "dataset_id", "provider")
        if key in source
    }
    identity["type"] = source.get(
        "kind", "controlled_private_h5ad" if request.get("import_id") else "measured_rna"
    )
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
        "import_id": request.get("import_id"),
        "dataset_id": request.get("dataset_id"),
        "condition_id": request.get("condition_id"),
        "source": identity,
        "summary": None,
        "attempt_no": row.attempt_no or 0,
        "cancel_requested": bool(row.cancel_requested),
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
                attempt_no=0,
                cancel_requested=0,
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

    def recover_expired(self) -> int:
        """Only expired leases may be recovered; an API restart has no ownership."""
        now = datetime.now(UTC)
        with self.sessions.begin() as session:
            expired = list(
                session.scalars(
                    select(Model.id).where(
                        Model.status.in_(["preparing", "analysing"]),
                        or_(Model.lease_expires_at < now, Model.lease_expires_at.is_(None)),
                    )
                )
            )
            count = 0
            for identifier in expired:
                result = session.execute(
                    update(Model)
                    .where(
                        Model.id == identifier,
                        Model.status.in_(["preparing", "analysing"]),
                        or_(Model.lease_expires_at < now, Model.lease_expires_at.is_(None)),
                    )
                    .values(
                        status="queued",
                        progress=0,
                        claim_token=None,
                        worker_id=None,
                        lease_expires_at=None,
                        message="租约到期，等待新 attempt 恢复",
                        updated_at=now,
                    )
                )
                if result.rowcount:
                    count += 1
                    session.execute(
                        update(Attempt)
                        .where(
                            Attempt.analysis_id == identifier,
                            Attempt.status == "running",
                        )
                        .values(status="abandoned", finished_at=now)
                    )
            # A queued cancellation is terminal even if no worker is running.
            session.execute(
                update(Model)
                .where(Model.status == "queued", Model.cancel_requested == 1)
                .values(status="cancelled", message="实测分析已取消", updated_at=now)
            )
            return count

    def claim(self, worker_id: str, lease_seconds: int, identifier: str | None = None) -> dict | None:
        now = datetime.now(UTC)
        with self.sessions() as session:
            query = select(Model.id).where(Model.status == "queued", Model.cancel_requested == 0)
            if identifier:
                query = query.where(Model.id == identifier)
            candidates = list(session.scalars(query.order_by(Model.created_at, Model.id).limit(20)))
        for candidate in candidates:
            token = uuid4().hex
            with self.sessions.begin() as session:
                result = session.execute(
                    update(Model)
                    .where(
                        Model.id == candidate,
                        Model.status == "queued",
                        Model.cancel_requested == 0,
                        Model.claim_token.is_(None),
                    )
                    .values(
                        status="preparing",
                        claim_token=token,
                        worker_id=worker_id,
                        lease_expires_at=now + timedelta(seconds=lease_seconds),
                        heartbeat_at=now,
                        updated_at=now,
                        attempt_no=Model.attempt_no + 1,
                        message="准备所选组合的真实数据",
                        error_message=None,
                    )
                )
                if result.rowcount != 1:
                    continue
                row = session.get(Model, candidate)
                session.add(
                    Attempt(
                        id=token,
                        analysis_id=candidate,
                        attempt_no=row.attempt_no,
                        worker_id=worker_id,
                        status="running",
                        started_at=now,
                    )
                )
                return {
                    "id": candidate,
                    "token": token,
                    "attempt_no": row.attempt_no,
                    "request": dict(row.request_json),
                }
        return None

    def heartbeat(self, identifier: str, token: str, lease_seconds: int) -> bool:
        now = datetime.now(UTC)
        with self.sessions.begin() as session:
            result = session.execute(
                update(Model)
                .where(
                    Model.id == identifier,
                    Model.claim_token == token,
                    Model.status.in_(ACTIVE),
                    Model.cancel_requested == 0,
                    Model.lease_expires_at >= now,
                )
                .values(heartbeat_at=now, lease_expires_at=now + timedelta(seconds=lease_seconds))
            )
            return result.rowcount == 1

    def owned_update(self, identifier: str, token: str, **values) -> bool:
        now = datetime.now(UTC)
        with self.sessions.begin() as session:
            result = session.execute(
                update(Model)
                .where(
                    Model.id == identifier,
                    Model.claim_token == token,
                    Model.status.in_(ACTIVE),
                    Model.cancel_requested == 0,
                    Model.lease_expires_at >= now,
                )
                .values(updated_at=now, **values)
            )
            return result.rowcount == 1

    def finish(self, identifier: str, token: str, status: str, *, publish=None, **values) -> bool:
        """Fence publication with a DB write lock; only its current lease may publish.

        If a process dies after the atomic rename and before commit, the next attempt
        verifies and adopts that same immutable result instead of overwriting it.
        """
        now = datetime.now(UTC)
        with self.sessions.begin() as session:
            conditions = [
                Model.id == identifier,
                Model.claim_token == token,
                Model.status.in_(ACTIVE),
                Model.lease_expires_at >= now,
            ]
            conditions.append(Model.cancel_requested == (1 if status == "cancelled" else 0))
            locked = session.execute(update(Model).where(*conditions).values(heartbeat_at=now))
            if locked.rowcount != 1:
                return False
            if publish:
                values.update(publish())
            session.execute(
                update(Model)
                .where(Model.id == identifier)
                .values(
                    status=status,
                    claim_token=None,
                    lease_expires_at=None,
                    updated_at=now,
                    **values,
                )
            )
            session.execute(
                update(Attempt)
                .where(Attempt.id == token, Attempt.status == "running")
                .values(status=status, finished_at=now, error_message=values.get("error_message"))
            )
            return True

    def cancel(self, identifier: str) -> dict:
        now = datetime.now(UTC)
        with self.sessions.begin() as session:
            session.execute(
                update(Model)
                .where(Model.id == identifier, Model.status.in_(ACTIVE))
                .values(cancel_requested=1, message="已请求取消，等待 worker 确认", updated_at=now)
            )
            session.execute(
                update(Model)
                .where(Model.id == identifier, Model.status == "queued")
                .values(status="cancelled", message="实测分析已取消", updated_at=now)
            )
        return self.get(identifier)[0]

    def attempts(self, identifier: str) -> list[dict]:
        with self.sessions() as session:
            rows = session.scalars(
                select(Attempt).where(Attempt.analysis_id == identifier).order_by(Attempt.attempt_no)
            )
            return [
                {
                    "attempt_no": row.attempt_no,
                    "status": row.status,
                    "started_at": row.started_at.isoformat(),
                    "finished_at": row.finished_at.isoformat() if row.finished_at else None,
                    "error_message": row.error_message,
                }
                for row in rows
            ]

    def interrupt_active(self) -> None:
        # Compatibility entry point deliberately obeys leases, not process startup.
        self.recover_expired()
