from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from .contracts import ConfirmDraftRequest, DingTalkLiveFetchRequest, GapResolutionRequest
from .contracts import IngestMessageResponse, IncomingMessage, KnowledgeSyncRequest
from .knowledge import KnowledgeService
from .orchestrator import AutoPmOrchestrator
from .storage import get_store

router = APIRouter(prefix="/api/auto-pm", tags=["auto-pm"])


def _orchestrator() -> AutoPmOrchestrator:
    return AutoPmOrchestrator(store=get_store())


def _knowledge() -> KnowledgeService:
    return KnowledgeService(store=get_store())


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/messages/ingest", response_model=IngestMessageResponse)
def ingest_message(message: IncomingMessage) -> IngestMessageResponse:
    return _orchestrator().ingest_message(message)


@router.post("/dingtalk/events", response_model=IngestMessageResponse)
def ingest_dingtalk_event(payload: dict[str, Any]) -> IngestMessageResponse:
    owner = str(payload.get("owner_id") or "")
    at_users = payload.get("atUsers") or payload.get("at_users") or []
    mentioned_owner = bool(payload.get("mentioned_owner"))
    if not mentioned_owner and owner and isinstance(at_users, list):
        for item in at_users:
            if isinstance(item, dict) and str(item.get("staffId") or item.get("userid") or "") == owner:
                mentioned_owner = True
                break

    text_value = ""
    if isinstance(payload.get("text"), dict):
        text_value = str(payload["text"].get("content") or "")
    elif isinstance(payload.get("text"), str):
        text_value = payload["text"].strip()
    elif isinstance(payload.get("content"), str):
        text_value = payload["content"].strip()

    raw_type = str(payload.get("conversationType") or payload.get("channel_type") or "private").lower()
    channel_type = "private" if raw_type in {"private", "single", "1"} else "group"
    message = IncomingMessage(
        message_id=str(payload.get("msgId") or payload.get("message_id") or payload.get("messageId") or ""),
        thread_id=str(payload.get("conversationId") or payload.get("thread_id") or payload.get("conversation_id") or ""),
        sender=str(payload.get("senderNick") or payload.get("senderId") or payload.get("sender") or "unknown"),
        text=text_value,
        channel_type=channel_type,
        mentioned_owner=mentioned_owner,
        metadata=payload,
    )
    if not message.message_id or not message.thread_id or not message.text:
        raise HTTPException(status_code=400, detail="Missing message_id, thread_id, or text in DingTalk payload")
    return _orchestrator().ingest_message(message)


@router.get("/drafts/{draft_id}")
def get_draft(draft_id: str):
    draft = get_store().get_draft(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft


@router.post("/drafts/{draft_id}/confirm")
def confirm_draft(draft_id: str, request: ConfirmDraftRequest):
    updated = get_store().update_draft(
        draft_id,
        draft_text=request.edited_text,
        status="sent" if request.mark_as_sent else "confirmed",
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return {"draft": updated, "dispatch_required": not bool(request.mark_as_sent)}


@router.post("/knowledge/sync")
def sync_knowledge(request: KnowledgeSyncRequest):
    return _knowledge().sync_source(request)


@router.post("/knowledge/dingtalk-project/live-fetch")
def live_fetch_dingtalk_project_doc(request: DingTalkLiveFetchRequest):
    try:
        return _knowledge().live_fetch_dingtalk_document(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/knowledge/tree")
def knowledge_tree():
    return _knowledge().knowledge_tree()


@router.get("/gaps")
def list_gaps(status: str | None = None):
    return get_store().list_gaps(status=status)


@router.post("/gaps/{gap_id}/resolve")
def resolve_gap(gap_id: str, request: GapResolutionRequest):
    gap = get_store().resolve_gap(gap_id, request.status)
    if gap is None:
        raise HTTPException(status_code=404, detail="Gap not found")
    return gap

