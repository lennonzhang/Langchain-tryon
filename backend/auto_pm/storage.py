from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .contracts import GapRecord, NotificationRecord, ReplyDraft
from .settings import database_path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AutoPmStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = Path(db_path or database_path())
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sources (
                    source_key TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    source_path TEXT,
                    project_id TEXT,
                    project_name TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    source_key TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    project_id TEXT,
                    project_name TEXT,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    content TEXT NOT NULL,
                    sync_mode TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sections (
                    section_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    heading TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    level INTEGER NOT NULL,
                    summary TEXT NOT NULL,
                    content TEXT NOT NULL,
                    keywords_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS drafts (
                    id TEXT PRIMARY KEY,
                    source_message_id TEXT NOT NULL,
                    recipient_thread TEXT NOT NULL,
                    requester TEXT NOT NULL,
                    draft_text TEXT NOT NULL,
                    citations_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    answer_status TEXT NOT NULL,
                    gap_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS gaps (
                    id TEXT PRIMARY KEY,
                    question TEXT NOT NULL,
                    requester TEXT NOT NULL,
                    missing_requirement TEXT NOT NULL,
                    missing_scope_json TEXT NOT NULL,
                    impact_analysis TEXT NOT NULL,
                    visited_nodes_json TEXT NOT NULL,
                    related_docs_json TEXT NOT NULL,
                    evidence_snippets_json TEXT NOT NULL,
                    suggested_followups_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS notifications (
                    id TEXT PRIMARY KEY,
                    gap_id TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    body TEXT NOT NULL,
                    sent_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS message_events (
                    message_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    accepted INTEGER NOT NULL,
                    reason TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def _json_dump(value) -> str:
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _json_load(value: str):
        return json.loads(value) if value else []

    def upsert_source(
        self,
        *,
        source_key: str,
        source_type: str,
        source_path: str | None,
        project_id: str | None,
        project_name: str | None,
        updated_at: str,
    ) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sources(source_key, source_type, source_path, project_id, project_name, updated_at)
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_key) DO UPDATE SET
                    source_type=excluded.source_type,
                    source_path=excluded.source_path,
                    project_id=excluded.project_id,
                    project_name=excluded.project_name,
                    updated_at=excluded.updated_at
                """,
                (source_key, source_type, source_path, project_id, project_name, updated_at),
            )

    def replace_source_documents(self, source_key: str, documents: list[dict]) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM sections WHERE document_id IN (SELECT document_id FROM documents WHERE source_key = ?)", (source_key,))
            conn.execute("DELETE FROM documents WHERE source_key = ?", (source_key,))
            for doc in documents:
                conn.execute(
                    """
                    INSERT INTO documents(
                        document_id, source_key, source_type, source_path, project_id, project_name,
                        title, summary, content, sync_mode, source_url, content_hash, updated_at, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        doc["document_id"],
                        source_key,
                        doc["source_type"],
                        doc["source_path"],
                        doc.get("project_id"),
                        doc.get("project_name"),
                        doc["title"],
                        doc["summary"],
                        doc["content"],
                        doc["sync_mode"],
                        doc.get("source_url", ""),
                        doc["content_hash"],
                        doc["updated_at"],
                        self._json_dump(doc.get("metadata", {})),
                    ),
                )
                for section in doc["sections"]:
                    conn.execute(
                        """
                        INSERT INTO sections(section_id, document_id, heading, position, level, summary, content, keywords_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            section["section_id"],
                            doc["document_id"],
                            section["heading"],
                            section["position"],
                            section["level"],
                            section["summary"],
                            section["content"],
                            self._json_dump(section["keywords"]),
                        ),
                    )

    def upsert_live_document(self, source_key: str, doc: dict) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM sections WHERE document_id = ?", (doc["document_id"],))
            conn.execute("DELETE FROM documents WHERE document_id = ?", (doc["document_id"],))
            conn.execute(
                """
                INSERT INTO documents(
                    document_id, source_key, source_type, source_path, project_id, project_name,
                    title, summary, content, sync_mode, source_url, content_hash, updated_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc["document_id"],
                    source_key,
                    doc["source_type"],
                    doc["source_path"],
                    doc.get("project_id"),
                    doc.get("project_name"),
                    doc["title"],
                    doc["summary"],
                    doc["content"],
                    doc["sync_mode"],
                    doc.get("source_url", ""),
                    doc["content_hash"],
                    doc["updated_at"],
                    self._json_dump(doc.get("metadata", {})),
                ),
            )
            for section in doc["sections"]:
                conn.execute(
                    """
                    INSERT INTO sections(section_id, document_id, heading, position, level, summary, content, keywords_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        section["section_id"],
                        doc["document_id"],
                        section["heading"],
                        section["position"],
                        section["level"],
                        section["summary"],
                        section["content"],
                        self._json_dump(section["keywords"]),
                    ),
                )

    def list_sources(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM sources ORDER BY source_type, source_key").fetchall()
        return [dict(row) for row in rows]

    def list_documents(self) -> list[dict]:
        with self._connect() as conn:
            docs = [dict(row) for row in conn.execute("SELECT * FROM documents ORDER BY source_type, source_path, title").fetchall()]
            sections = [dict(row) for row in conn.execute("SELECT * FROM sections ORDER BY document_id, position").fetchall()]
        sections_by_doc: dict[str, list[dict]] = {}
        for row in sections:
            row["keywords"] = self._json_load(row.pop("keywords_json"))
            sections_by_doc.setdefault(row["document_id"], []).append(row)
        for doc in docs:
            doc["metadata"] = self._json_load(doc.pop("metadata_json"))
            doc["sections"] = sections_by_doc.get(doc["document_id"], [])
        return docs

    def get_draft(self, draft_id: str) -> ReplyDraft | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
        if row is None:
            return None
        payload = dict(row)
        payload["citations"] = self._json_load(payload.pop("citations_json"))
        return ReplyDraft.model_validate(payload)

    def create_draft(self, draft: ReplyDraft) -> ReplyDraft:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO drafts(id, source_message_id, recipient_thread, requester, draft_text, citations_json, status, answer_status, gap_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    draft.id,
                    draft.source_message_id,
                    draft.recipient_thread,
                    draft.requester,
                    draft.draft_text,
                    self._json_dump([item.model_dump() for item in draft.citations]),
                    draft.status,
                    draft.answer_status,
                    draft.gap_id,
                    draft.created_at,
                    draft.updated_at,
                ),
            )
        return draft

    def update_draft(self, draft_id: str, *, draft_text: str | None = None, status: str | None = None) -> ReplyDraft | None:
        draft = self.get_draft(draft_id)
        if draft is None:
            return None
        if draft_text is not None:
            draft.draft_text = draft_text
        if status is not None:
            draft.status = status
        draft.updated_at = _utc_now()
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE drafts SET draft_text = ?, status = ?, updated_at = ? WHERE id = ?",
                (draft.draft_text, draft.status, draft.updated_at, draft.id),
            )
        return draft

    def create_gap(self, gap: GapRecord) -> GapRecord:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO gaps(id, question, requester, missing_requirement, missing_scope_json, impact_analysis, visited_nodes_json, related_docs_json, evidence_snippets_json, suggested_followups_json, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    gap.id,
                    gap.question,
                    gap.requester,
                    gap.missing_requirement,
                    self._json_dump(gap.missing_scope),
                    gap.impact_analysis,
                    self._json_dump(gap.visited_nodes),
                    self._json_dump(gap.related_docs),
                    self._json_dump(gap.evidence_snippets),
                    self._json_dump(gap.suggested_followups),
                    gap.status,
                    gap.created_at,
                    gap.updated_at,
                ),
            )
        return gap

    def list_gaps(self, status: str | None = None) -> list[GapRecord]:
        query = "SELECT * FROM gaps"
        params: tuple = ()
        if status:
            query += " WHERE status = ?"
            params = (status,)
        query += " ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        result: list[GapRecord] = []
        for row in rows:
            payload = dict(row)
            payload["missing_scope"] = self._json_load(payload.pop("missing_scope_json"))
            payload["visited_nodes"] = self._json_load(payload.pop("visited_nodes_json"))
            payload["related_docs"] = self._json_load(payload.pop("related_docs_json"))
            payload["evidence_snippets"] = self._json_load(payload.pop("evidence_snippets_json"))
            payload["suggested_followups"] = self._json_load(payload.pop("suggested_followups_json"))
            result.append(GapRecord.model_validate(payload))
        return result

    def resolve_gap(self, gap_id: str, status: str) -> GapRecord | None:
        gaps = {gap.id: gap for gap in self.list_gaps()}
        gap = gaps.get(gap_id)
        if gap is None:
            return None
        gap.status = status
        gap.updated_at = _utc_now()
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE gaps SET status = ?, updated_at = ? WHERE id = ?", (gap.status, gap.updated_at, gap.id))
        return gap

    def create_notification(self, notification: NotificationRecord) -> NotificationRecord:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO notifications(id, gap_id, recipient, channel, body, sent_at) VALUES (?, ?, ?, ?, ?, ?)",
                (notification.id, notification.gap_id, notification.recipient, notification.channel, notification.body, notification.sent_at),
            )
        return notification

    def record_message_event(self, *, message_id: str, payload: dict, accepted: bool, reason: str | None, created_at: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO message_events(message_id, payload_json, accepted, reason, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(message_id) DO UPDATE SET
                    payload_json=excluded.payload_json,
                    accepted=excluded.accepted,
                    reason=excluded.reason,
                    created_at=excluded.created_at
                """,
                (message_id, self._json_dump(payload), 1 if accepted else 0, reason, created_at),
            )

    @staticmethod
    def new_id(prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:12]}"


_STORE: AutoPmStore | None = None


def get_store() -> AutoPmStore:
    global _STORE
    if _STORE is None:
        _STORE = AutoPmStore()
    return _STORE


def reset_store(db_path: Path | None = None) -> AutoPmStore:
    global _STORE
    _STORE = AutoPmStore(db_path=db_path)
    return _STORE
