import os
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.auto_pm.storage import reset_store
from backend.gateway.app import app


class TestAutoPmApi(unittest.TestCase):
    def setUp(self):
        self.test_root = Path.cwd() / ".tmp-auto-pm-tests" / uuid.uuid4().hex
        self.data_dir = self.test_root / "data"
        self.docs_dir = self.test_root / "docs"
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(self.test_root, ignore_errors=True))
        self.env_patcher = patch.dict(
            os.environ,
            {
                "AUTO_PM_DATA_DIR": str(self.data_dir),
                "AUTO_PM_OWNER_ID": "owner-1",
                "AUTO_PM_OWNER_NAME": "PM Owner",
                "AUTO_PM_DINGTALK_PROJECT_IDS": "proj-1",
            },
            clear=False,
        )
        self.env_patcher.start()
        self.addCleanup(self.env_patcher.stop)
        reset_store(self.data_dir / "autopm.sqlite3")
        self.client = TestClient(app)
        self.llm_patcher = patch("backend.auto_pm.model_provider.AutoPmModelProvider._llm_answer", return_value=None)
        self.llm_patcher.start()
        self.addCleanup(self.llm_patcher.stop)

    def test_sync_tree_and_answered_ingest_flow(self):
        (self.docs_dir / "login.md").write_text(
            "# 登录说明\n\n## 登录流程\n用户输入账号密码后进入首页。\n",
            encoding="utf-8",
        )
        sync = self.client.post(
            "/api/auto-pm/knowledge/sync",
            json={"source_type": "obsidian", "source_path": str(self.docs_dir)},
        )
        self.assertEqual(sync.status_code, 200)
        self.assertEqual(sync.json()["document_count"], 1)

        tree = self.client.get("/api/auto-pm/knowledge/tree")
        self.assertEqual(tree.status_code, 200)
        self.assertEqual(tree.json()[0]["node_type"], "source")

        response = self.client.post(
            "/api/auto-pm/messages/ingest",
            json={
                "message_id": "msg-1",
                "thread_id": "thread-1",
                "sender": "dev-a",
                "text": "登录流程是什么？",
                "channel_type": "private",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["accepted"])
        self.assertEqual(body["answer"]["status"], "answered")
        self.assertIsNotNone(body["draft"]["id"])
        self.assertEqual(body["gap"], None)

    def test_group_message_without_mention_is_ignored(self):
        response = self.client.post(
            "/api/auto-pm/messages/ingest",
            json={
                "message_id": "msg-ignore",
                "thread_id": "thread-ignore",
                "sender": "dev-b",
                "text": "帮我看一下这个需求",
                "channel_type": "group",
                "mentioned_owner": False,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["accepted"])
        self.assertIn("outside the owner proxy scope", response.json()["reason"])

    def test_doc_gap_creates_gap_and_notification(self):
        (self.docs_dir / "login.md").write_text(
            "# 登录说明\n\n## 登录流程\n用户输入账号密码后进入首页。\n",
            encoding="utf-8",
        )
        self.client.post(
            "/api/auto-pm/knowledge/sync",
            json={"source_type": "obsidian", "source_path": str(self.docs_dir)},
        )
        response = self.client.post(
            "/api/auto-pm/messages/ingest",
            json={
                "message_id": "msg-gap",
                "thread_id": "thread-gap",
                "sender": "dev-c",
                "text": "登录流程的权限范围是什么？",
                "channel_type": "private",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["answer"]["status"], "doc_gap")
        self.assertIn("权限范围", body["gap"]["missing_scope"])
        self.assertIsNotNone(body["notification"]["id"])

        gaps = self.client.get("/api/auto-pm/gaps")
        self.assertEqual(gaps.status_code, 200)
        self.assertEqual(len(gaps.json()), 1)

        resolved = self.client.post(
            f"/api/auto-pm/gaps/{body['gap']['id']}/resolve",
            json={"status": "resolved"},
        )
        self.assertEqual(resolved.status_code, 200)
        self.assertEqual(resolved.json()["status"], "resolved")

    def test_confirm_draft_and_live_fetch_dingtalk_document(self):
        fetch = self.client.post(
            "/api/auto-pm/knowledge/dingtalk-project/live-fetch",
            json={
                "project_id": "proj-1",
                "project_name": "Proj One",
                "doc_id": "doc-1",
                "title": "支付需求",
                "content": "# 支付需求\n\n## 支付流程\n用户确认订单后调用支付。\n",
                "source_url": "https://example.test/doc-1",
            },
        )
        self.assertEqual(fetch.status_code, 200)
        self.assertEqual(fetch.json()["sync_mode"], "live_fetched")

        ingest = self.client.post(
            "/api/auto-pm/messages/ingest",
            json={
                "message_id": "msg-draft",
                "thread_id": "thread-draft",
                "sender": "dev-d",
                "text": "支付流程是什么？",
                "channel_type": "private",
            },
        )
        self.assertEqual(ingest.status_code, 200)
        draft_id = ingest.json()["draft"]["id"]

        confirm = self.client.post(
            f"/api/auto-pm/drafts/{draft_id}/confirm",
            json={"edited_text": "请按支付流程文档实现。", "mark_as_sent": False},
        )
        self.assertEqual(confirm.status_code, 200)
        self.assertEqual(confirm.json()["draft"]["status"], "confirmed")
        self.assertEqual(confirm.json()["draft"]["draft_text"], "请按支付流程文档实现。")
