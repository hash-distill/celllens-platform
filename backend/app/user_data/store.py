import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from backend.app.core.errors import ScientificContractError
from backend.app.core.storage import RunStore
from backend.app.user_data.auth import DUMMY_PASSWORD, check_password, hash_password, token_hash
from backend.app.user_data.models import DatasetModel, SessionModel, UserAnalysisModel, UserModel
from backend.app.user_data.schemas import UserCreateRequest


def now() -> datetime:
    # Naive UTC is portable between MySQL and SQLite; API dates explicitly carry Z.
    return datetime.now(UTC).replace(tzinfo=None)


def iso(value: datetime) -> str:
    return value.isoformat() + "Z"


def public_user(row: UserModel) -> dict[str, Any]:
    return {"id": row.id, "username": row.username, "role": row.role}


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

    def create_user(self, username: str, password: str, role: str = "user") -> dict[str, Any]:
        request = UserCreateRequest(username=username, password=password, role=role)  # type: ignore[arg-type]
        row = UserModel(
            id="usr_" + uuid.uuid4().hex,
            username=request.username.lower(),
            password_hash=hash_password(password),
            role=role,
            active=True,
            created_at=now(),
        )
        try:
            with self.sessions.begin() as session:
                session.add(row)
        except IntegrityError as exc:
            raise ValueError("用户名已存在") from exc
        return public_user(row)

    def login(self, username: str, password: str, ttl_seconds: int) -> tuple[str, dict[str, Any]] | None:
        with self.sessions.begin() as session:
            user = session.scalar(
                select(UserModel).where(UserModel.username == username.lower()).with_for_update()
            )
            valid = check_password(password, user.password_hash if user else DUMMY_PASSWORD)
            if user is None:
                return None
            if not user.active or (user.locked_until and user.locked_until > now()):
                return None
            if not valid:
                user.failed_logins += 1
                if user.failed_logins >= 5:
                    user.locked_until = now() + timedelta(minutes=15)
                    user.failed_logins = 0
                return None
            user.failed_logins = 0
            user.locked_until = None
            token, csrf = secrets.token_urlsafe(32), secrets.token_hex(32)
            session.execute(delete(SessionModel).where(SessionModel.expires_at <= now()))
            session.add(
                SessionModel(
                    token_hash=token_hash(token),
                    user_id=user.id,
                    csrf_token=csrf,
                    expires_at=now() + timedelta(seconds=ttl_seconds),
                )
            )
            return token, {**public_user(user), "csrf_token": csrf}

    def authenticate(self, token: str) -> dict[str, Any] | None:
        with self.sessions() as session:
            result = session.execute(
                select(UserModel, SessionModel)
                .join(SessionModel, SessionModel.user_id == UserModel.id)
                .where(
                    SessionModel.token_hash == token_hash(token),
                    SessionModel.expires_at > now(),
                    UserModel.active.is_(True),
                )
            ).first()
            if result is None:
                return None
            user, ticket = result
            return {**public_user(user), "csrf_token": ticket.csrf_token}

    def logout(self, token: str) -> None:
        with self.sessions.begin() as session:
            session.execute(delete(SessionModel).where(SessionModel.token_hash == token_hash(token)))

    def reset_password(self, username: str, password: str) -> None:
        UserCreateRequest(username=username, password=password)
        with self.sessions.begin() as session:
            user = session.scalar(select(UserModel).where(UserModel.username == username.lower()))
            if user is None:
                raise ValueError("用户不存在")
            user.password_hash = hash_password(password)
            user.failed_logins = 0
            user.locked_until = None
            session.execute(delete(SessionModel).where(SessionModel.user_id == user.id))

    def dataset(self, dataset_id: str, owner_id: str) -> dict[str, Any] | None:
        with self.sessions() as session:
            row = session.scalar(
                select(DatasetModel).where(DatasetModel.id == dataset_id, DatasetModel.owner_id == owner_id)
            )
            return public_dataset(row) if row else None

    def datasets(self, owner_id: str, limit: int, offset: int) -> dict[str, Any]:
        with self.sessions() as session:
            query = select(DatasetModel).where(DatasetModel.owner_id == owner_id)
            total = session.scalar(select(func.count()).select_from(query.subquery()))
            rows = session.scalars(query.order_by(DatasetModel.created_at.desc()).limit(limit).offset(offset))
            return {"items": [public_dataset(row) for row in rows], "total": total}

    def used_bytes(self, owner_id: str) -> int:
        with self.sessions() as session:
            return int(
                session.scalar(
                    select(func.coalesce(func.sum(DatasetModel.size_bytes), 0)).where(
                        DatasetModel.owner_id == owner_id
                    )
                )
                or 0
            )

    def add_dataset(
        self,
        *,
        owner_id: str,
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

    def archive(self, dataset_id: str, owner_id: str) -> None:
        with self.sessions.begin() as session:
            row = session.scalar(
                select(DatasetModel)
                .where(DatasetModel.id == dataset_id, DatasetModel.owner_id == owner_id)
                .with_for_update()
            )
            if row:
                row.archived = True

    def create_analysis(self, owner_id: str, request: dict) -> dict[str, Any]:
        with self.sessions.begin() as session:
            # Lock the user row so simultaneous submissions cannot exceed the quota.
            session.scalar(select(UserModel).where(UserModel.id == owner_id).with_for_update())
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
                raise ValueError("最多同时保留 3 个待完成分析任务")
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

    def analysis(self, analysis_id: str, owner_id: str) -> dict[str, Any] | None:
        with self.sessions() as session:
            row = session.scalar(
                select(UserAnalysisModel).where(
                    UserAnalysisModel.id == analysis_id, UserAnalysisModel.owner_id == owner_id
                )
            )
            return public_analysis(row) if row else None

    def analyses(self, owner_id: str, limit: int, offset: int) -> dict[str, Any]:
        with self.sessions() as session:
            query = select(UserAnalysisModel).where(UserAnalysisModel.owner_id == owner_id)
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
                .where(UserAnalysisModel.status.in_(["queued", "running"]))
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
