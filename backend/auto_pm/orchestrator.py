from __future__ import annotations

from .account_gateway import AccountGatewayService
from .contracts import AskResponse, GapRecord, IncomingMessage, IngestMessageResponse, ReplyDraft
from .knowledge import KnowledgeService
from .model_provider import AutoPmModelProvider
from .notifications import NotificationService
from .storage import AutoPmStore, get_store


class AutoPmOrchestrator:
    def __init__(
        self,
        *,
        store: AutoPmStore | None = None,
        knowledge_service: KnowledgeService | None = None,
        model_provider: AutoPmModelProvider | None = None,
        notification_service: NotificationService | None = None,
        account_gateway: AccountGatewayService | None = None,
    ) -> None:
        self._store = store or get_store()
        self._knowledge = knowledge_service or KnowledgeService(self._store)
        self._models = model_provider or AutoPmModelProvider()
        self._notifications = notification_service or NotificationService(self._store)
        self._account_gateway = account_gateway or AccountGatewayService()

    def ingest_message(self, message: IncomingMessage) -> IngestMessageResponse:
        accepted, reason = self._account_gateway.should_process_message(message)
        self._store.record_message_event(
            message_id=message.message_id,
            payload=message.model_dump(),
            accepted=accepted,
            reason=reason,
            created_at=message.occurred_at,
        )
        if not accepted:
            return IngestMessageResponse(accepted=False, reason=reason)

        evidence, visited_nodes = self._knowledge.search(message.text)
        citations = self._knowledge.citations_from_matches(evidence)
        decision = self._models.answer_question(
            question=message.text,
            evidence=evidence,
            citations=citations,
            visited_nodes=visited_nodes,
        )
        answer = AskResponse(
            status=decision["status"],
            answer=decision["answer"],
            citations=citations,
            related_clues=list(decision.get("related_clues", [])),
            visited_nodes=list(decision.get("visited_nodes", visited_nodes)),
        )
        gap = None
        notification = None
        if answer.status == "doc_gap":
            gap = self._store.create_gap(
                GapRecord(
                    id=self._store.new_id("gap"),
                    question=message.text,
                    requester=message.sender,
                    missing_requirement=str(decision.get("missing_requirement") or "当前文档未明确说明"),
                    missing_scope=list(decision.get("missing_scope", [])),
                    impact_analysis=str(decision.get("impact_analysis") or ""),
                    visited_nodes=answer.visited_nodes,
                    related_docs=[item.source_path for item in citations],
                    evidence_snippets=[item.snippet for item in citations],
                    suggested_followups=list(decision.get("suggested_followups", [])),
                )
            )
            answer.gap_id = gap.id
            notification = self._notifications.notify_gap(gap)

        draft = self._store.create_draft(
            ReplyDraft(
                id=self._store.new_id("draft"),
                source_message_id=message.message_id,
                recipient_thread=message.thread_id,
                requester=message.sender,
                draft_text=answer.answer,
                citations=citations,
                status="pending",
                answer_status=answer.status,
                gap_id=gap.id if gap else None,
            )
        )
        answer.draft_id = draft.id
        return IngestMessageResponse(
            accepted=True,
            draft=draft,
            gap=gap,
            notification=notification,
            answer=answer,
        )

