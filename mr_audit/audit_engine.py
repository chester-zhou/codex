from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Sequence

from .excel_parser import AuditRule
from .pdf_parser import PdfPage
from .qwen_client import call_qwen_json


@dataclass
class EvidenceItem:
    page: int
    quote: str


@dataclass
class AuditResult:
    major: str
    minor: str
    requirement: str
    result: str
    evidence: List[EvidenceItem]
    reason: str
    confidence: float


CJK_RE = re.compile(r"[\u4e00-\u9fff]+")


def _extract_keywords(text: str, limit: int = 18) -> List[str]:
    if not text:
        return []

    keywords: List[str] = []
    seen = set()

    # Chinese sequences
    for seq in CJK_RE.findall(text):
        if len(seq) <= 6:
            if seq not in seen:
                keywords.append(seq)
                seen.add(seq)
        else:
            for size in (2, 3, 4):
                for i in range(0, len(seq) - size + 1, 2):
                    token = seq[i : i + size]
                    if token not in seen:
                        keywords.append(token)
                        seen.add(token)
                    if len(keywords) >= limit:
                        return keywords

    # Non-Chinese tokens
    for token in re.split(r"\W+", text):
        token = token.strip()
        if len(token) >= 3 and token not in seen:
            keywords.append(token)
            seen.add(token)
        if len(keywords) >= limit:
            break

    return keywords


def _score_page(text: str, keywords: Sequence[str]) -> int:
    if not text or not keywords:
        return 0
    score = 0
    for kw in keywords:
        if kw:
            score += text.count(kw)
    return score


def _extract_snippet(text: str, keyword: str, window: int = 60) -> Optional[str]:
    if not keyword:
        return None
    idx = text.find(keyword)
    if idx < 0:
        return None
    start = max(0, idx - window)
    end = min(len(text), idx + len(keyword) + window)
    snippet = text[start:end].replace("\n", " ").strip()
    return snippet


def find_evidence(pages: Sequence[PdfPage], rule: AuditRule, max_items: int = 3) -> List[EvidenceItem]:
    keywords = _extract_keywords(f"{rule.requirement} {rule.standard}")
    scored_pages = []
    for page in pages:
        score = _score_page(page.text, keywords)
        if score > 0:
            scored_pages.append((score, page))

    scored_pages.sort(key=lambda x: x[0], reverse=True)

    evidence: List[EvidenceItem] = []
    for _, page in scored_pages[: max_items * 2]:
        for kw in keywords:
            snippet = _extract_snippet(page.text, kw)
            if snippet:
                evidence.append(EvidenceItem(page=page.page_num, quote=snippet))
                if len(evidence) >= max_items:
                    return evidence
    return evidence


def _build_prompt(rule: AuditRule, evidence: List[EvidenceItem]) -> str:
    evidence_payload = [asdict(item) for item in evidence]
    return (
        "你是 MR 场地安装图纸审核助手。请仅基于给定证据做判断。\n"
        "若证据不足或无法确认，请返回 UNKNOWN。\n"
        "要求输出严格 JSON，字段为: result, confidence, reason, evidence。\n"
        "result 只能是 PASS/FAIL/UNKNOWN。confidence 取 0-1 小数。\n"
        f"审核要点: {rule.requirement}\n"
        f"合格标准: {rule.standard}\n"
        f"证据: {json.dumps(evidence_payload, ensure_ascii=False)}"
    )


def audit_rules(
    rules: Sequence[AuditRule],
    pages: Sequence[PdfPage],
    *,
    model: Optional[str] = None,
    skip_llm: bool = False,
    max_evidence: int = 3,
) -> List[AuditResult]:
    results: List[AuditResult] = []
    system_prompt = "你是严格遵守 JSON 输出的工程审核助手。"

    for rule in rules:
        evidence = find_evidence(pages, rule, max_items=max_evidence)
        if not evidence:
            results.append(
                AuditResult(
                    major=rule.major,
                    minor=rule.minor,
                    requirement=rule.requirement,
                    result="UNKNOWN",
                    evidence=[],
                    reason="图纸中未找到可验证的相关证据",
                    confidence=0.0,
                )
            )
            continue

        if skip_llm:
            results.append(
                AuditResult(
                    major=rule.major,
                    minor=rule.minor,
                    requirement=rule.requirement,
                    result="UNKNOWN",
                    evidence=evidence,
                    reason="已找到证据，但跳过大模型判断",
                    confidence=0.0,
                )
            )
            continue

        user_prompt = _build_prompt(rule, evidence)
        try:
            response = call_qwen_json(system_prompt, user_prompt, model=model)
            result = str(response.get("result", "UNKNOWN")).upper()
            if result not in {"PASS", "FAIL", "UNKNOWN"}:
                result = "UNKNOWN"
            confidence = float(response.get("confidence", 0))
            reason = str(response.get("reason", ""))
            ev_items = response.get("evidence")
            if isinstance(ev_items, list):
                evidence = [
                    EvidenceItem(page=int(item.get("page", 0)), quote=str(item.get("quote", "")))
                    for item in ev_items
                    if isinstance(item, dict)
                ] or evidence
        except Exception as exc:
            result = "UNKNOWN"
            confidence = 0.0
            reason = f"大模型调用失败: {exc}"

        results.append(
            AuditResult(
                major=rule.major,
                minor=rule.minor,
                requirement=rule.requirement,
                result=result,
                evidence=evidence,
                reason=reason,
                confidence=confidence,
            )
        )

    return results
