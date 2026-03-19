from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from backend.config import load_api_key
from backend.message_builder import extract_text
from backend.model_profile import proxy_env_guard, stream_or_invoke_kwargs
from backend.provider_router import build_routed_chat_model

from .contracts import Citation, EvidenceSnippet
from .settings import auto_pm_model_id

_SCOPE_KEYWORDS = {
    "适用对象": ("对象", "用户", "角色", "适用", "scope"),
    "流程边界": ("流程", "步骤", "边界", "入口", "出口"),
    "前置条件": ("前置", "条件", "依赖", "准备"),
    "异常处理": ("异常", "失败", "错误", "重试", "回滚"),
    "权限范围": ("权限", "授权", "角色", "审批"),
    "时间范围": ("时间", "生效", "截止", "周期"),
    "上下游依赖": ("接口", "系统", "上游", "下游", "依赖"),
}


def _extract_json_object(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    stripped = text.strip()
    candidates = [stripped, re.sub(r"^```json|```$", "", stripped, flags=re.MULTILINE).strip()]
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match is None:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


class AutoPmModelProvider:
    def answer_question(
        self,
        *,
        question: str,
        evidence: list[EvidenceSnippet],
        citations: list[Citation],
        visited_nodes: list[str],
    ) -> dict[str, Any]:
        fallback = self._heuristic_answer(question=question, evidence=evidence, citations=citations, visited_nodes=visited_nodes)
        structured = self._llm_answer(question=question, evidence=evidence, citations=citations, visited_nodes=visited_nodes)
        if structured is None:
            return fallback
        structured.setdefault("citations", [item.model_dump() for item in citations])
        structured.setdefault("related_clues", visited_nodes[:3])
        structured.setdefault("visited_nodes", visited_nodes)
        if structured.get("status") not in {"answered", "inferred", "doc_gap"}:
            return fallback
        return structured

    def _llm_answer(
        self,
        *,
        question: str,
        evidence: list[EvidenceSnippet],
        citations: list[Citation],
        visited_nodes: list[str],
    ) -> dict[str, Any] | None:
        try:
            api_key = load_api_key()
            model_id = auto_pm_model_id()
            client = build_routed_chat_model(api_key=api_key, model=model_id, thinking_mode=False)
            payload = {
                "question": question,
                "visited_nodes": visited_nodes,
                "citations": [item.model_dump() for item in citations],
                "evidence": [item.model_dump() for item in evidence[:4]],
            }
            with proxy_env_guard():
                response = client.invoke(
                    [
                        SystemMessage(
                            content=(
                                "You are Auto-PM. Return only JSON with keys status, answer, "
                                "missing_requirement, missing_scope, impact_analysis, suggested_followups, related_clues. "
                                "Use status answered, inferred, or doc_gap. Prefer doc_gap over guessing."
                            )
                        ),
                        HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
                    ],
                    **stream_or_invoke_kwargs(model_id, False),
                )
        except Exception:
            return None
        return _extract_json_object(extract_text(getattr(response, "content", "")))

    def _heuristic_answer(
        self,
        *,
        question: str,
        evidence: list[EvidenceSnippet],
        citations: list[Citation],
        visited_nodes: list[str],
    ) -> dict[str, Any]:
        if not evidence:
            missing_scope = self._missing_scope(question, "")
            return {
                "status": "doc_gap",
                "answer": "当前知识库中没有找到可直接支撑该问题的需求描述。",
                "missing_requirement": "未检索到直接相关的需求说明或范围约束。",
                "missing_scope": missing_scope,
                "impact_analysis": "研发可能基于假设推进实现，后续容易出现返工或跨系统对齐偏差。",
                "suggested_followups": [
                    "补充该需求的适用对象和流程边界",
                    "明确异常处理、权限或时间生效条件",
                ],
                "related_clues": visited_nodes[:3],
                "visited_nodes": visited_nodes,
                "citations": [item.model_dump() for item in citations],
            }

        best = evidence[0]
        combined = "\n".join(item.content for item in evidence[:3])
        missing_scope = self._missing_scope(question, combined)
        if best.score >= 4 and not missing_scope:
            return {
                "status": "answered",
                "answer": (
                    f"根据当前文档，相关描述集中在《{best.document_title}》的“{best.section_title}”部分：\n"
                    + "\n".join(f"- {item.snippet}" for item in citations[:3])
                ),
                "missing_requirement": "",
                "missing_scope": [],
                "impact_analysis": "",
                "suggested_followups": [],
                "related_clues": visited_nodes[:3],
                "visited_nodes": visited_nodes,
                "citations": [item.model_dump() for item in citations],
            }
        if missing_scope:
            return {
                "status": "doc_gap",
                "answer": "找到了相关文档线索，但当前文档没有把这个问题需要的范围约束写清楚。",
                "missing_requirement": "文档包含相关背景，但缺少可以直接回答该问题的明确范围说明。",
                "missing_scope": missing_scope,
                "impact_analysis": "如果在缺少范围边界的情况下继续实现，容易导致权限、流程或异常分支与真实需求偏离。",
                "suggested_followups": [f"明确{item}" for item in missing_scope],
                "related_clues": visited_nodes[:3],
                "visited_nodes": visited_nodes,
                "citations": [item.model_dump() for item in citations],
            }
        return {
            "status": "inferred",
            "answer": "当前文档没有直接给出完整结论，但结合相关描述可以做出有限推断。",
            "missing_requirement": "",
            "missing_scope": [],
            "impact_analysis": "",
            "suggested_followups": [],
            "related_clues": visited_nodes[:3],
            "visited_nodes": visited_nodes,
            "citations": [item.model_dump() for item in citations],
        }

    def _missing_scope(self, question: str, evidence_text: str) -> list[str]:
        missing: list[str] = []
        for label, keywords in _SCOPE_KEYWORDS.items():
            asks = any(keyword in question for keyword in keywords)
            covered = any(keyword in evidence_text for keyword in keywords)
            if asks and not covered:
                missing.append(label)
        return missing
