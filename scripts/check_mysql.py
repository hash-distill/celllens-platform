"""Verify the configured MySQL schema and a complete durable run round trip."""

import argparse
import uuid

from sqlalchemy import delete, inspect

from backend.app.config import get_settings
from backend.app.core.errors import JobAlreadyClaimedError
from backend.app.core.storage import RunStore
from backend.app.db.models import RunModel
from backend.app.schemas import CreateRunRequest, RunStatus

EXPECTED_TABLES = {
    "alembic_version",
    "runs",
    "run_attempts",
    "run_events",
    "run_artifacts",
    "run_cache",
    "users",
    "user_sessions",
    "user_datasets",
    "user_analyses",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--connection-only", action="store_true", help="Check connection before schema migration"
    )
    args = parser.parse_args()
    store = RunStore(get_settings().database_url)
    if args.connection_only:
        store.ping()
        print("MySQL connection: OK")
        return
    tables = set(inspect(store.engine).get_table_names())
    missing = EXPECTED_TABLES - tables
    if missing:
        raise RuntimeError(f"Missing MySQL tables: {sorted(missing)}")
    with store.named_lock("celllens:mysql-smoke-lock", timeout_seconds=1):
        try:
            with store.named_lock("celllens:mysql-smoke-lock", timeout_seconds=0):
                raise AssertionError("Second connection unexpectedly acquired the shared lock")
        except JobAlreadyClaimedError:
            pass
    run_id = f"smoke_{uuid.uuid4().hex[:12]}"
    try:
        store.create(run_id, CreateRunRequest(cell_line="K562", perturbation="MYC"))
        attempt = store.start_attempt(run_id, worker_id="mysql-smoke", lease_seconds=60)
        store.transition(run_id, RunStatus.STATE_RUNNING, 15)
        store.transition(run_id, RunStatus.FAILED, 15, error_code="SMOKE_COMPLETE")
        store.finish_attempt(attempt.id, succeeded=False, error_code="SMOKE_COMPLETE")
        assert store.get(run_id).error_code == "SMOKE_COMPLETE"
        assert len(store.events(run_id)) == 3
    finally:
        with store.session_factory.begin() as session:
            session.execute(delete(RunModel).where(RunModel.run_id == run_id))
    print("MySQL schema and durable run round trip: OK")
    print("Tables:", ", ".join(sorted(tables)))


if __name__ == "__main__":
    main()
