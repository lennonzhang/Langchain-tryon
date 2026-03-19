from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .contracts import Citation, DingTalkLiveFetchRequest, DingTalkProjectDocument
from .contracts import EvidenceSnippet, KnowledgeNode, KnowledgeSyncRequest, utc_now_iso
from .settings import dingtalk_project_root, dingtalk_project_whitelist
from .storage import AutoPmStore, get_store

_SUPPORTED_EXTENSIONS = {".md", ".txt"}


def tokenize_text(text: str) -> list[str]:
    lowered = (text or "").lower()
    tokens: set[str] = set()
    for raw in re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", lowered):
        token = raw.strip()
        if not token:
            continue
        tokens.add(token)
        if re.fullmatch(r"[\u4e00-\u9fff]{2,}", token):
            for idx in range(len(token) - 1):
                tokens.add(token[idx : idx + 2])
    return sorted(tokens)


def summarize_text(text: str, limit: int = 160) -> str:
    cleaned = " ".join(line.strip() for line in text.splitlines() if line.strip())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "..."


def split_markdown_sections(title: str, content: str) -> list[dict]:
    sections: list[dict] = []
    current_heading = title or "Overview"
    current_level = 1
    current_lines: list[str] = []

    def flush(position: int) -> None:
        section_text = "\n".join(current_lines).strip() or content.strip()
        if not section_text and sections:
            return
        section_id = hashlib.sha1(f"{title}:{current_heading}:{position}".encode("utf-8")).hexdigest()[:16]
        sections.append(
            {
                "section_id": section_id,
                "heading": current_heading,
                "position": position,
                "level": current_level,
                "summary": summarize_text(section_text),
                "content": section_text,
                "keywords": tokenize_text(f"{current_heading}\n{section_text}")[:20],
            }
        )

    for line in content.splitlines():
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            if current_lines or not sections:
                flush(len(sections))
            current_heading = match.group(2).strip()
            current_level = len(match.group(1))
            current_lines = []
        else:
            current_lines.append(line)
    flush(len(sections))
    return sections


class KnowledgeService:
    def __init__(self, store: AutoPmStore | None = None) -> None:
        self._store = store or get_store()

    def sync_source(self, request: KnowledgeSyncRequest) -> dict:
        source_key = self._source_key(request.source_type, request.source_path, request.project_id)
        self._store.upsert_source(
            source_key=source_key,
            source_type=request.source_type,
            source_path=request.source_path,
            project_id=request.project_id,
            project_name=request.project_name,
            updated_at=utc_now_iso(),
        )
        documents = self._load_documents_for_source(request)
        self._store.replace_source_documents(source_key, documents)
        return {
            "accepted": True,
            "source_key": source_key,
            "source_type": request.source_type,
            "document_count": len(documents),
            "section_count": sum(len(item["sections"]) for item in documents),
        }

    def live_fetch_dingtalk_document(self, request: DingTalkLiveFetchRequest) -> DingTalkProjectDocument:
        whitelist = dingtalk_project_whitelist()
        if whitelist and request.project_id not in whitelist:
            raise ValueError(f"project_id '{request.project_id}' is not allowed")
        source_key = self._source_key("dingtalk_project", None, request.project_id)
        self._store.upsert_source(
            source_key=source_key,
            source_type="dingtalk_project",
            source_path="",
            project_id=request.project_id,
            project_name=request.project_name,
            updated_at=utc_now_iso(),
        )
        document = self._build_document(
            source_type="dingtalk_project",
            source_path=f"dingtalk://{request.project_id}/{request.doc_id}",
            title=request.title,
            content=request.content,
            sync_mode="live_fetched",
            project_id=request.project_id,
            project_name=request.project_name,
            source_url=request.source_url,
        )
        document["document_id"] = request.doc_id
        self._store.upsert_live_document(source_key, document)
        return DingTalkProjectDocument(
            project_id=request.project_id,
            project_name=request.project_name,
            doc_id=request.doc_id,
            doc_title=request.title,
            source_url=request.source_url,
            sync_mode="live_fetched",
        )

    def knowledge_tree(self) -> list[KnowledgeNode]:
        docs = self._store.list_documents()
        roots: dict[str, KnowledgeNode] = {}
        for doc in docs:
            source_type = doc["source_type"]
            root = roots.setdefault(
                source_type,
                KnowledgeNode(
                    node_id=f"source:{source_type}",
                    node_type="source",
                    title=source_type,
                    summary=f"{source_type} documents",
                    source_type=source_type,
                ),
            )
            parent = root
            if source_type == "dingtalk_project" and doc.get("project_id"):
                project_node_id = f"project:{doc['project_id']}"
                project_node = next((item for item in parent.children if item.node_id == project_node_id), None)
                if project_node is None:
                    project_node = KnowledgeNode(
                        node_id=project_node_id,
                        node_type="project",
                        title=doc.get("project_name") or str(doc["project_id"]),
                        summary=f"DingTalk project {doc['project_id']}",
                        source_type=source_type,
                    )
                    parent.children.append(project_node)
                parent = project_node
            for folder in [part for part in Path(doc["source_path"]).parts[:-1] if part not in {"", "."}][-4:]:
                folder_node_id = f"{parent.node_id}/folder:{folder}"
                folder_node = next((item for item in parent.children if item.node_id == folder_node_id), None)
                if folder_node is None:
                    folder_node = KnowledgeNode(
                        node_id=folder_node_id,
                        node_type="folder",
                        title=folder,
                        source_type=source_type,
                    )
                    parent.children.append(folder_node)
                parent = folder_node
            doc_node = KnowledgeNode(
                node_id=f"document:{doc['document_id']}",
                node_type="document",
                title=doc["title"],
                summary=doc["summary"],
                source_type=source_type,
                source_path=doc["source_path"],
                updated_at=doc["updated_at"],
            )
            for section in doc["sections"][:10]:
                doc_node.children.append(
                    KnowledgeNode(
                        node_id=f"section:{section['section_id']}",
                        node_type="section",
                        title=section["heading"],
                        summary=section["summary"],
                        source_type=source_type,
                        source_path=doc["source_path"],
                        updated_at=doc["updated_at"],
                    )
                )
            parent.children.append(doc_node)
        return list(roots.values())

    def search(self, question: str, limit: int = 5) -> tuple[list[EvidenceSnippet], list[str]]:
        tokens = set(tokenize_text(question))
        matches: list[EvidenceSnippet] = []
        visited_nodes: list[str] = []
        for doc in self._store.list_documents():
            title_tokens = set(tokenize_text(doc["title"]))
            path_tokens = set(tokenize_text(doc["source_path"]))
            for section in doc["sections"]:
                heading_tokens = set(tokenize_text(section["heading"]))
                body_tokens = set(section["keywords"])
                score = float(
                    len(tokens & title_tokens) * 3
                    + len(tokens & heading_tokens) * 4
                    + len(tokens & body_tokens)
                    + len(tokens & path_tokens)
                )
                if score <= 0:
                    continue
                matches.append(
                    EvidenceSnippet(
                        document_id=doc["document_id"],
                        section_id=section["section_id"],
                        score=score,
                        source_type=doc["source_type"],
                        source_path=doc["source_path"],
                        document_title=doc["title"],
                        section_title=section["heading"],
                        content=section["content"][:1200],
                    )
                )
                visited_nodes.append(f"{doc['source_type']} > {doc['title']} > {section['heading']}")
        matches.sort(key=lambda item: item.score, reverse=True)
        seen_nodes: list[str] = []
        for item in visited_nodes:
            if item not in seen_nodes:
                seen_nodes.append(item)
        return matches[:limit], seen_nodes[:limit]

    def citations_from_matches(self, matches: list[EvidenceSnippet], limit: int = 3) -> list[Citation]:
        citations: list[Citation] = []
        for item in matches[:limit]:
            citations.append(
                Citation(
                    source_type=item.source_type,
                    source_path=item.source_path,
                    document_title=item.document_title,
                    section_title=item.section_title,
                    snippet=summarize_text(item.content, limit=220),
                )
            )
        return citations

    def _load_documents_for_source(self, request: KnowledgeSyncRequest) -> list[dict]:
        source_root = self._resolve_source_path(request)
        if source_root is None or not source_root.exists():
            return []
        documents: list[dict] = []
        for file_path in sorted(source_root.rglob("*")):
            if not file_path.is_file() or file_path.suffix.lower() not in _SUPPORTED_EXTENSIONS:
                continue
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            title = self._title_from_content(file_path, content)
            documents.append(
                self._build_document(
                    source_type=request.source_type,
                    source_path=str(file_path.relative_to(source_root)),
                    title=title,
                    content=content,
                    sync_mode="synced",
                    project_id=request.project_id,
                    project_name=request.project_name,
                )
            )
        return documents

    def _resolve_source_path(self, request: KnowledgeSyncRequest) -> Path | None:
        if request.source_path:
            return Path(request.source_path)
        if request.source_type == "dingtalk_project" and request.project_id:
            root = dingtalk_project_root()
            if root is None:
                return None
            return root / request.project_id
        return None

    def _build_document(
        self,
        *,
        source_type: str,
        source_path: str,
        title: str,
        content: str,
        sync_mode: str,
        project_id: str | None = None,
        project_name: str | None = None,
        source_url: str = "",
    ) -> dict:
        content_hash = hashlib.sha1(content.encode("utf-8")).hexdigest()
        document_id = hashlib.sha1(f"{source_type}:{project_id or ''}:{source_path}".encode("utf-8")).hexdigest()[:16]
        return {
            "document_id": document_id,
            "source_type": source_type,
            "source_path": source_path,
            "project_id": project_id,
            "project_name": project_name,
            "title": title,
            "summary": summarize_text(content),
            "content": content,
            "sync_mode": sync_mode,
            "source_url": source_url,
            "content_hash": content_hash,
            "updated_at": utc_now_iso(),
            "metadata": {},
            "sections": split_markdown_sections(title, content),
        }

    @staticmethod
    def _title_from_content(file_path: Path, content: str) -> str:
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                return stripped.lstrip("#").strip()
            return stripped[:80]
        return file_path.stem

    @staticmethod
    def _source_key(source_type: str, source_path: str | None, project_id: str | None) -> str:
        return f"{source_type}:{project_id or ''}:{source_path or ''}"
