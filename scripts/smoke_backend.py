"""Run one real MySQL + GPU STATE + scCellFie API smoke test."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from backend.app.main import create_app


def main() -> int:
    with TestClient(create_app()) as client:
        health = client.get("/api/v1/health")
        ready = client.get("/api/v1/ready")
        print("health", health.status_code, health.json())
        print("ready", ready.status_code, ready.json())
        health.raise_for_status()
        ready.raise_for_status()

        created = client.post(
            "/api/v1/runs",
            json={
                "cell_line": "K562",
                "perturbation": "MYC",
                "mode": "online",
                "n_cells": 64,
                "seed": 42,
            },
        )
        print("create", created.status_code, created.json())
        created.raise_for_status()
        run_id = created.json()["run_id"]
        if created.json()["cache_hit"]:
            print("cache hit", run_id)
        else:
            deadline = time.monotonic() + 600
            while time.monotonic() < deadline:
                record = client.get(f"/api/v1/runs/{run_id}").json()
                print("run", record["status"], record["stage_progress"])
                if record["status"] in {"completed", "failed"}:
                    break
                time.sleep(1)
            if record["status"] != "completed":
                raise RuntimeError(f"run did not complete: {record}")

        for suffix in ("summary", "projection", "genes", "metabolic-tasks", "reactions", "report"):
            response = client.get(f"/api/v1/runs/{run_id}/{suffix}")
            print(suffix, response.status_code, len(response.content))
            response.raise_for_status()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
