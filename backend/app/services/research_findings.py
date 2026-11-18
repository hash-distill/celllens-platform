"""Persistent user annotations referencing an exact, immutable result fingerprint."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select

from backend.app.db.research_models import ResearchFindingModel
from backend.app.services.research_results import ResearchResults


def document(row):
    return {
        "id": row.id,
        "record_kind": row.record_kind,
        "record_id": row.record_id,
        "result_id": f"{row.record_kind}:{row.record_id}",
        "manifest_sha256": row.manifest_sha256,
        "fingerprint_basis": row.fingerprint_basis,
        "selection": row.selection_json,
        "note": row.note,
        "created_at": row.created_at.isoformat(),
    }


class ResearchFindings:
    def __init__(self, container):
        self.sessions = container.store.session_factory
        self.results = ResearchResults(container)

    def create(self, kind, identifier, selection, note):
        if not isinstance(note, str) or len(note) > 4000:
            raise ValueError("发现注释最多 4000 个字符")
        if not note.strip() and not any(selection.values()):
            raise ValueError("请保存一个选择或填写发现注释")
        result = self.results.validate_selection(kind, identifier, selection)
        with self.sessions.begin() as session:
            row = ResearchFindingModel(
                id="finding_" + uuid4().hex[:24],
                record_kind=kind,
                record_id=identifier,
                manifest_sha256=result["provenance"]["manifest_sha256"],
                fingerprint_basis=result["provenance"]["fingerprint_basis"],
                selection_json=selection,
                note=note.strip(),
                created_at=datetime.now(UTC),
            )
            session.add(row)
            return document(row)

    def list(self, kind=None, identifier=None, limit=50, offset=0):
        filters = []
        if kind:
            filters.append(ResearchFindingModel.record_kind == kind)
        if identifier:
            filters.append(ResearchFindingModel.record_id == identifier)
        with self.sessions() as session:
            total = session.scalar(select(func.count()).select_from(ResearchFindingModel).where(*filters))
            rows = session.scalars(
                select(ResearchFindingModel)
                .where(*filters)
                .order_by(ResearchFindingModel.created_at.desc(), ResearchFindingModel.id)
                .limit(limit)
                .offset(offset)
            )
            return {
                "items": [document(row) for row in rows],
                "total": total,
                "limit": limit,
                "offset": offset,
            }

    def for_export(self, kind, identifier):
        page = self.list(kind, identifier, limit=10001)
        if page["total"] > 10000:
            raise ValueError("发现数量超过单次导出上限，请分页下载发现列表")
        return page["items"]
