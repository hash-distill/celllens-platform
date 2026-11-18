from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/runs", tags=["run operations"])


@router.post("/{run_id}/cancel")
def cancel_run(run_id: str, request: Request):
    try:
        return request.app.state.container.store.cancel(run_id)
    except KeyError as exc:
        raise HTTPException(404, "Run not found") from exc


@router.get("/{run_id}/attempts")
def run_attempts(run_id: str, request: Request):
    store = request.app.state.container.store
    try:
        store.get(run_id)
    except KeyError as exc:
        raise HTTPException(404, "Run not found") from exc
    return {"items": store.attempts(run_id), "events": [vars(event) for event in store.events(run_id)]}
