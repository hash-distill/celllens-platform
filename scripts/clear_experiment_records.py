"""Explicit one-off cleanup with a durable row backup; source/artifact files stay intact."""

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select

from backend.app.config import Settings
from backend.app.container import build_container
from backend.app.db.models import RunArtifactModel, RunAttemptModel, RunCacheModel, RunEventModel, RunModel

TABLES = [RunCacheModel, RunArtifactModel, RunAttemptModel, RunEventModel, RunModel]


def clear_records(store, backup: Path) -> dict[str, int]:
    with store.session_factory.begin() as session:
        rows = {}
        for model in TABLES:
            statement = select(model.__table__).with_for_update()
            rows[model.__tablename__] = [dict(row) for row in session.execute(statement).mappings()]
        for name in ("runs",):
            if any(row["status"] not in ("completed", "failed") for row in rows[name]):
                raise RuntimeError("Cannot clear records while experiments are active")
        document = {
            "created_at": datetime.now(UTC).isoformat(),
            "tables": rows,
            "note": "Database rows only; original datasets and result files preserved.",
        }
        backup.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation + fsync: deletion cannot start without a durable backup.
        with backup.open("x", encoding="utf-8") as target:
            json.dump(document, target, default=lambda value: value.isoformat(), ensure_ascii=False, indent=2)
            target.flush()
            os.fsync(target.fileno())
        for model in TABLES:
            saved = rows[model.__tablename__]
            if not saved:
                continue
            keys = list(model.__table__.primary_key.columns)
            if len(keys) != 1:
                raise RuntimeError("Cleanup expects a single primary key")
            key = keys[0]
            session.execute(delete(model).where(key.in_([row[key.name] for row in saved])))
    return {name: len(saved) for name, saved in rows.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Back up and remove current completed/failed records"
    )
    args = parser.parse_args()
    if not args.apply:
        parser.error("Explicit --apply is required")
    settings = Settings()
    container = build_container(settings)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    backup = settings.project_root / "output" / "record-backups" / f"records-{stamp}.json"
    counts = clear_records(container.store, backup)
    print(json.dumps({"backup": str(backup), "deleted": counts}, ensure_ascii=False))


if __name__ == "__main__":
    main()
