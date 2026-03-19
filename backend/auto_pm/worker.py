from __future__ import annotations

import time

from .contracts import KnowledgeSyncRequest
from .knowledge import KnowledgeService
from .settings import dingtalk_project_root, dingtalk_project_whitelist, worker_poll_seconds


class AutoPmWorker:
    def __init__(self, knowledge_service: KnowledgeService | None = None) -> None:
        self._knowledge = knowledge_service or KnowledgeService()

    def run_once(self) -> list[dict]:
        results: list[dict] = []
        root = dingtalk_project_root()
        for project_id in sorted(dingtalk_project_whitelist()):
            request = KnowledgeSyncRequest(
                source_type="dingtalk_project",
                source_path=str(root / project_id) if root is not None else None,
                project_id=project_id,
                project_name=project_id,
            )
            results.append(self._knowledge.sync_source(request))
        return results

    def run_forever(self) -> None:
        while True:
            self.run_once()
            time.sleep(worker_poll_seconds())

