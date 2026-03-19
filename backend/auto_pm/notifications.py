from __future__ import annotations

from .contracts import GapRecord, NotificationRecord
from .settings import owner_id
from .storage import AutoPmStore, get_store


class NotificationService:
    def __init__(self, store: AutoPmStore | None = None) -> None:
        self._store = store or get_store()

    def notify_gap(self, gap: GapRecord) -> NotificationRecord:
        body = (
            f"Auto-PM 缺口通知\n"
            f"提问人: {gap.requester}\n"
            f"问题: {gap.question}\n"
            f"缺失点: {gap.missing_requirement}\n"
            f"缺少 scope: {', '.join(gap.missing_scope) or '未明确'}\n"
            f"影响分析: {gap.impact_analysis}"
        )
        notification = NotificationRecord(
            id=self._store.new_id("notif"),
            gap_id=gap.id,
            recipient=owner_id(),
            channel="dingtalk",
            body=body,
        )
        return self._store.create_notification(notification)

