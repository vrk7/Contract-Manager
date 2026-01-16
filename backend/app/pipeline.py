from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from typing import Any, Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .guards import ensure_retrieval_guardrails, filter_malicious_segments
from .llm import AnthropicClient, LLMUsage
from .models import Analysis, PlaybookChunk, PlaybookVersion
from .rag import PlaybookRAG, chunk_playbook
from .schemas import AnalysisResult, Finding, GuardrailWarning, RetrievedChunk, Usage

logger = logging.getLogger(__name__)


def _extract_clauses(contract_text: str) -> list[dict[str, str]]:
    """
    Lightweight deterministic clause extraction. Focuses on key risk areas.
    """
    patterns = [
        ("payment_terms", r"within\s+(\d+)\s+days", "days"),
        ("retainage", r"retain(?:age)?\s+(\d+)%", "%"),
        ("notice_period", r"within\s+(\d+)\s+(?:calendar\s+)?days.*notice", "days"),
        ("indemnification", r"indemnif\w+.*?(regardless of fault|any and all)", ""),
        ("termination_notice", r"terminate.*?(\d+)\s+calendar\s+days", "days"),
        ("dispute_resolution", r"arbitration.*?in\s+([A-Za-z\s]+)", "location"),
        ("liquidated_damages", r"€?([\d,\.]+)\s*per\s*(?:calendar\s*)?day", "currency"),
    ]
    findings: list[dict[str, str]] = []
    for clause_type, pattern, unit in patterns:
        for match in re.finditer(pattern, contract_text, flags=re.IGNORECASE):
            value = match.group(1) if match.groups() else match.group(0)
            span_text = contract_text[max(0, match.start() - 50) : match.end() + 50]
            findings.append(
                {
                    "clause_type": clause_type,
                    "extracted_value": f"{value} {unit}".strip(),
                    "source_text": span_text.strip(),
                }
            )
    return findings


def _compare_with_playbook(
    clause: dict[str, str],
    retrieved: list[RetrievedChunk],
) -> tuple[str, str, str]:
    """
    Compute playbook standard, deviation, and risk level using retrieved chunk text.
    """
    standard = "See playbook reference"
    deviation = "No deviation detected"
    risk_level = "medium"
    text = " ".join(chunk.content for chunk in retrieved)
    try:
        value_num = None
        if clause["clause_type"] in {"payment_terms", "notice_period", "termination_notice"}:
            digits = re.findall(r"(\d+)", clause["extracted_value"])
            value_num = int(digits[0]) if digits else None
        if clause["clause_type"] == "retainage":
            digits = re.findall(r"(\d+)", clause["extracted_value"])
            value_num = int(digits[0]) if digits else None

        if clause["clause_type"] == "payment_terms" and value_num is not None:
            standard_match = re.search(r"(\d+)[-–](\d+)\s*days", text)
            if standard_match:
                low, high = int(standard_match.group(1)), int(standard_match.group(2))
                standard = f"{low}-{high} days"
                if value_num > 90:
                    deviation, risk_level = ">90 days vs standard", "critical"
                elif value_num > 60:
                    deviation, risk_level = f"{value_num} days (above 60)", "high"
                elif value_num > high:
                    deviation, risk_level = f"{value_num} vs {standard}", "medium"
                else:
                    deviation, risk_level = "Within standard", "low"
        elif clause["clause_type"] == "retainage" and value_num is not None:
            standard_match = re.search(r"(\d+)%", text)
            if standard_match:
                standard = f"{standard_match.group(1)}%"
            if value_num > 15:
                deviation, risk_level = "Retainage above 15%", "critical"
            elif value_num > 10:
                deviation, risk_level = "Retainage above 10%", "high"
            elif value_num > 5:
                deviation, risk_level = "Retainage above 5%", "medium"
            else:
                deviation, risk_level = "Within standard", "low"
        elif clause["clause_type"] == "notice_period" and value_num is not None:
            standard = "14-21 days" if "14-21 days" in text else "See playbook"
            if value_num <= 3:
                deviation, risk_level = "≤3 days with waiver risk", "critical"
            elif value_num <= 6:
                deviation, risk_level = "Short notice window", "high"
            elif value_num < 14:
                deviation, risk_level = "Below preferred 14 days", "medium"
            else:
                deviation, risk_level = "Within preferred range", "low"
        elif clause["clause_type"] == "indemnification":
            standard = "Limit to proportionate fault"
            if re.search(r"regardless of fault|any and all", clause["source_text"], re.I):
                deviation, risk_level = "Broad form indemnity", "critical"
            else:
                deviation, risk_level = "Broad language detected", "high"
        elif clause["clause_type"] == "termination_notice" and value_num is not None:
            standard = "30+ days" if "30+" in text or "30 days" in text else "See playbook"
            if value_num < 7:
                deviation, risk_level = "<7 days", "critical"
            elif value_num < 14:
                deviation, risk_level = "7-13 days", "high"
            elif value_num < 30:
                deviation, risk_level = "14-29 days", "medium"
            else:
                deviation, risk_level = "Within acceptable range", "low"
        elif clause["clause_type"] == "dispute_resolution":
            standard = "Neutral venue"
            if re.search(r"owner", clause["source_text"], re.I):
                deviation, risk_level = "Owner's venue", "high"
            else:
                deviation, risk_level = "Check neutrality", "medium"
        elif clause["clause_type"] == "liquidated_damages":
            standard = "0.1-0.2%/day with cap"
            if re.search(r"€?75,?000", clause["extracted_value"]):
                deviation, risk_level = "High daily LD", "high"
            else:
                deviation, risk_level = "Within playbook range", "low"
        else:
            deviation, risk_level = "Needs review", "medium"
    except Exception as exc:
        logger.exception("Comparison error: %s", exc)
    return standard, deviation, risk_level


def _friendly_clause_label(clause_type: str) -> str:
    labels = {
        "payment_terms": "Payment timing",
        "retainage": "Retainage",
        "notice_period": "Notice period",
        "indemnification": "Indemnification scope",
        "termination_notice": "Termination notice",
        "dispute_resolution": "Dispute resolution",
        "liquidated_damages": "Liquidated damages",
    }
    return labels.get(clause_type, clause_type.replace("_", " ").title())


def _overall_risk(findings: list[Finding]) -> str:
    levels = ["unknown", "acceptable", "low", "medium", "high", "critical"]
    max_idx = 0
    for finding in findings:
        idx = levels.index(finding.risk_level)
        max_idx = max(max_idx, idx)
    return levels[max_idx]


def _risk_index(level: str) -> int:
    ordering = ["unknown", "acceptable", "low", "medium", "high", "critical"]
    return ordering.index(level) if level in ordering else 0


def _format_citation_ids(retrieved_chunks: list[RetrievedChunk]) -> str:
    ids = [chunk.chunk_id for chunk in retrieved_chunks]
    return "; ".join(ids)


def _merge_findings(findings: list[Finding]) -> list[Finding]:
    merged: dict[str, Finding] = {}
    for finding in findings:
        existing = merged.get(finding.clause_type)
        if not existing:
            merged[finding.clause_type] = finding
            continue
        # Choose the higher-risk finding as the base
        base = finding if _risk_index(finding.risk_level) >= _risk_index(existing.risk_level) else existing
        other = existing if base is finding else finding
        # Merge chunk citations, preserving order and uniqueness
        chunk_map = {chunk.chunk_id: chunk for chunk in base.retrieved_chunks}
        for chunk in other.retrieved_chunks:
            if chunk.chunk_id not in chunk_map:
                base.retrieved_chunks.append(chunk)
        # Prefer longer source text for context
        if len(other.source_text) > len(base.source_text):
            base.source_text = other.source_text
        # Preserve playbook standard and deviation from the higher-risk finding
        base.playbook_standard = base.playbook_standard or other.playbook_standard
        base.deviation = base.deviation or other.deviation
        # Keep the extracted value from the higher-risk finding
        base.extracted_value = base.extracted_value or other.extracted_value
        merged[finding.clause_type] = base
    return list(merged.values())


async def run_analysis_pipeline(
    session: AsyncSession | None,
    analysis: Analysis,
    streamer: Callable[[str, Any], Awaitable[None] | None] | None = None,
    playbook_content_override: str | None = None,
    initial_guardrails: list[GuardrailWarning] | None = None,
) -> AnalysisResult:
    async def _emit(event: str, data: Any) -> None:
        if not streamer:
            return
        result = streamer(event, data)
        if asyncio.iscoroutine(result):
            await result

    guardrails: list[GuardrailWarning] = list(initial_guardrails or [])
    # Guardrails: sanitize input
    sanitized_text, extra_warnings = filter_malicious_segments(analysis.contract_text)
    guardrails.extend(extra_warnings)
    analysis.contract_text = sanitized_text
    if session:
        await session.flush()

    # Clause extraction
    extracted_clauses = _extract_clauses(sanitized_text)
    await _emit(
        "status",
        {"analysis_id": analysis.id, "status": "extracting", "message": "Extracted clauses"},
    )

    # Determine playbook version
    version_id = analysis.playbook_version_id
    if playbook_content_override:
        version_id = "in-memory"
    if not version_id and session:
        result = await session.execute(
            select(PlaybookVersion).order_by(PlaybookVersion.created_at.desc())
        )
        latest = result.scalars().first()
        if latest:
            version_id = latest.id
            analysis.playbook_version_id = version_id

    rag = PlaybookRAG()
    if playbook_content_override:
        chunks = chunk_playbook(playbook_content_override)
        rag.reset_version(version_id, [(f"{version_id}-{idx}", text) for idx, text in enumerate(chunks)])
    findings: list[Finding] = []
    llm_client = AnthropicClient()
    total_usage = LLMUsage(0, 0)

    for clause in extracted_clauses:
        retrieved_chunks: list[RetrievedChunk] = []
        if version_id:
            retrieved_chunks = rag.query(version_id, clause["source_text"])
        if not retrieved_chunks:
            continue
        standard, deviation, risk_level = _compare_with_playbook(clause, retrieved_chunks)
        citation_ids = _format_citation_ids(retrieved_chunks)
        prompt_text = (
            f"Clause type: {clause['clause_type']}. "
            f"Extracted: {clause['extracted_value']}. "
            f"Playbook excerpts: {' '.join(chunk.content for chunk in retrieved_chunks)}"
        )
        if analysis.analysis_type == "summary":
            summary_text = f"{_friendly_clause_label(clause['clause_type'])}: {clause['extracted_value']}"
            finding = Finding(
                clause_type=clause["clause_type"],
                extracted_value=clause["extracted_value"],
                playbook_standard=standard,
                deviation=deviation,
                risk_level=risk_level,  # type: ignore[arg-type]
                recommendation=f"Summary: {summary_text}. Cite chunks: {citation_ids}.",
                source_text=clause["source_text"],
                retrieved_chunks=retrieved_chunks,
            )
            # Estimate token usage for telemetry parity
            total_usage.input_tokens += len(prompt_text) // 4
            total_usage.output_tokens += len(finding.recommendation) // 4
        elif analysis.analysis_type == "obligations":
            obligation_text = f"Ensure compliance with {_friendly_clause_label(clause['clause_type']).lower()} ({clause['extracted_value']})."
            finding = Finding(
                clause_type=clause["clause_type"],
                extracted_value=clause["extracted_value"],
                playbook_standard=standard,
                deviation=deviation,
                risk_level=risk_level,  # type: ignore[arg-type]
                recommendation=f"Action: {obligation_text} Cite chunks: {citation_ids} for playbook guidance.",
                source_text=clause["source_text"],
                retrieved_chunks=retrieved_chunks,
            )
            total_usage.input_tokens += len(prompt_text) // 4
            total_usage.output_tokens += len(finding.recommendation) // 4
        else:
            prompt = (
                "You are validating construction contract clause alignment to the playbook. "
                f"Clause type: {clause['clause_type']}. Extracted: {clause['extracted_value']}. "
                f"Playbook guidance: {retrieved_chunks[0].content[:500]}"
            )
            _, usage = await llm_client.complete(prompt, max_tokens=256)
            total_usage.input_tokens += usage.input_tokens
            total_usage.output_tokens += usage.output_tokens
            finding = Finding(
                clause_type=clause["clause_type"],
                extracted_value=clause["extracted_value"],
                playbook_standard=standard,
                deviation=deviation,
                risk_level=risk_level,  # type: ignore[arg-type]
                recommendation=f"Negotiate toward playbook guidance. Cite chunks: {citation_ids}.",
                source_text=clause["source_text"],
                retrieved_chunks=retrieved_chunks,
            )
        findings.append(finding)
        await _emit(
            "partial_finding",
            {"analysis_id": analysis.id, "finding": finding.dict()},
        )

    # Drop invalid findings (missing source or retrieval)
    merged_findings = _merge_findings(findings)
    guardrails.extend(ensure_retrieval_guardrails([f.dict() for f in merged_findings]))
    merged_findings = [
        f
        for f in merged_findings
        if f.source_text
        and f.retrieved_chunks
    ]

    if not merged_findings:
        overall = "unknown"
        guardrails.append(
            GuardrailWarning(
                type="no_findings",
                message="No valid findings produced; overall risk set to unknown.",
                triggered_by="deduplication",
            )
        )
    else:
        overall = _overall_risk(merged_findings)
    usage_payload = Usage(
        input_tokens=total_usage.input_tokens,
        output_tokens=total_usage.output_tokens,
        total_tokens=total_usage.total_tokens,
        estimated_cost_usd=round(total_usage.estimated_cost, 6),
    )

    result = AnalysisResult(
        analysis_id=analysis.id,
        timestamp=datetime.utcnow(),
        overall_risk_score=overall,  # type: ignore[arg-type]
        findings=merged_findings,
        guardrail_warnings=guardrails,
        confidence_score=0.62 if merged_findings else 0.4,
        playbook_version_id=version_id,
        usage=usage_payload,
    )
    return result
