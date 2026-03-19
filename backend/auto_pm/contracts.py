from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Citation(BaseModel):
    source_type: str
    source_path: str
    document_title: str
    section_title: str
    snippet: str


class EvidenceSnippet(BaseModel):
    document_id: str
    section_id: str
    score: float
    source_type: str
    source_path: str
    document_title: str
    section_title: str
    content: str


class IncomingMessage(BaseModel):
    message_id: str
    thread_id: str
    sender: str
    text: str
    channel_type: Literal["private", "group"] = "private"
    mentioned_owner: bool = False
    occurred_at: str = Field(default_factory=utc_now_iso)
    platform: str = "dingtalk"
    metadata: dict = Field(default_factory=dict)


class ReplyDraft(BaseModel):
    id: str
    source_message_id: str
    recipient_thread: str
    requester: str
    draft_text: str
    citations: list[Citation] = Field(default_factory=list)
    status: Literal["pending", "confirmed", "sent", "rejected"] = "pending"
    answer_status: Literal["answered", "inferred", "doc_gap"] = "answered"
    gap_id: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class GapRecord(BaseModel):
    id: str
    question: str
    requester: str
    missing_requirement: str
    missing_scope: list[str] = Field(default_factory=list)
    impact_analysis: str
    visited_nodes: list[str] = Field(default_factory=list)
    related_docs: list[str] = Field(default_factory=list)
    evidence_snippets: list[str] = Field(default_factory=list)
    suggested_followups: list[str] = Field(default_factory=list)
    status: Literal["open", "resolved", "dismissed"] = "open"
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class NotificationRecord(BaseModel):
    id: str
    gap_id: str
    recipient: str
    channel: str
    body: str
    sent_at: str = Field(default_factory=utc_now_iso)


class KnowledgeNode(BaseModel):
    node_id: str
    node_type: Literal["source", "project", "folder", "document", "section"]
    title: str
    summary: str = ""
    scope_notes: str = ""
    keywords: list[str] = Field(default_factory=list)
    source_type: str = ""
    source_path: str = ""
    updated_at: str = Field(default_factory=utc_now_iso)
    children: list["KnowledgeNode"] = Field(default_factory=list)


class DingTalkProjectDocument(BaseModel):
    project_id: str
    project_name: str
    doc_id: str
    doc_title: str
    source_url: str = ""
    sync_mode: Literal["synced", "live_fetched"] = "synced"
    updated_at: str = Field(default_factory=utc_now_iso)


class KnowledgeSyncRequest(BaseModel):
    source_type: Literal["obsidian", "git", "dingtalk_project"]
    source_path: str | None = None
    project_id: str | None = None
    project_name: str | None = None


class DingTalkLiveFetchRequest(BaseModel):
    project_id: str
    project_name: str
    doc_id: str
    title: str
    content: str
    source_url: str = ""


class AskResponse(BaseModel):
    status: Literal["answered", "inferred", "doc_gap"]
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    related_clues: list[str] = Field(default_factory=list)
    visited_nodes: list[str] = Field(default_factory=list)
    gap_id: str | None = None
    draft_id: str | None = None


class IngestMessageResponse(BaseModel):
    accepted: bool
    reason: str | None = None
    draft: ReplyDraft | None = None
    gap: GapRecord | None = None
    notification: NotificationRecord | None = None
    answer: AskResponse | None = None


class ConfirmDraftRequest(BaseModel):
    edited_text: str | None = None
    mark_as_sent: bool = False


class GapResolutionRequest(BaseModel):
    status: Literal["resolved", "dismissed"]


KnowledgeNode.model_rebuild()

