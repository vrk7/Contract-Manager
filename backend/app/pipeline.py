from __future__ import annotations

import asyncio
import re
from datetime import datetime
from typing import Any, Awaitable, Callable

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .guards import ensure_retrieval_guardrails, filter_malicious_segments
from .llm import AnthropicClient, LLMUsage
from .models import Analysis, PlaybookVersion
from .rag import PlaybookRAG
from .rag import chunk_playbook_with_headings as chunk_playbook
from .risk_config import DEFAULT_RISK_CONFIG, score_numeric
from .schemas import AnalysisResult, Finding, GuardrailWarning, RetrievedChunk, Usage
from .utils import extract_first_number

logger = structlog.get_logger(__name__)


# Contracts longer than this are split into sections before extraction.
_LARGE_CONTRACT_THRESHOLD = 30_000  # ~6 pages

# Context characters captured around each regex match.
_CONTEXT_WINDOW = 300

# Maximum number of clauses sent to the LLM; lower-risk ones get heuristic-only findings.
_MAX_LLM_FINDINGS = 30

_PATTERNS: list[tuple[str, str, str]] = [
    ("payment_terms",          r"within\s+(\d+)\s+days",                                                    "days"),
    ("retainage",              r"retain(?:age)?\s+(\d+)%",                                                  "%"),
    ("notice_period",          r"within\s+(\d+)\s+(?:calendar\s+)?days.*?notice",                           "days"),
    ("indemnification",        r"indemnif\w+.*?(regardless of fault|any and all)",                           ""),
    ("termination_notice",     r"terminat\w+.*?(\d+)\s+calendar\s+days",                                    "days"),
    ("dispute_resolution",     r"arbitration.*?in\s+([A-Za-z\s]+)",                                         "location"),
    ("liquidated_damages",     r"€?([\d,\.]+)\s*per\s*(?:calendar\s*)?day",                                 "currency"),
    ("force_majeure",          r"force\s+majeure|act\s+of\s+(?:God|nature)|unforeseeable\s+(?:event|circumstance)", ""),
    ("warranty",               r"warrant\w*\s+(?:period\s+of\s+)?(\d+)\s+(?:year|month)",                   "period"),
    ("insurance",              r"insur\w+\s+(?:coverage|requirement)\w*.*?\$([\d,]+(?:\.\d+)?)",             "USD"),
    ("change_order",           r"change\s+orders?\s+.*?(?:markup|fee|overhead)\s+of\s+(\d+(?:\.\d+)?(?:\s*percent|%)?)",  "%"),
    ("substantial_completion", r"substantial\s+complet\w+.*?(\d+\s+days|[A-Z][a-z]+\s+\d+,?\s*\d{4})",     ""),
    ("delay_damages",          r"(?:delay\w*\s+damages|liquidated\s+damages\s+for\s+delay).*?\$([\d,]+)",   "USD"),
    ("governing_law",          r"governed\s+by\s+(?:the\s+)?laws?\s+of\s+(?:the\s+)?([A-Za-z ]+)",         "jurisdiction"),
    ("limitation_of_liability", r"liabilit\w+\s+(?:shall\s+)?not\s+exceed\s+\$?([\d,]+)",                  "USD"),
    ("non_compete",            r"non[- ]?compete|not\s+(?:to\s+)?compete|competing\s+business",            ""),
    ("ip_assignment",          r"intellectual\s+property.*?assign|work\s+made\s+for\s+hire",               ""),
    ("data_privacy",           r"personal\s+data|data\s+protection|GDPR|privacy\s+policy|data\s+breach",   ""),
    ("exclusivity",            r"exclusive\w*\s+(?:right|supplier|vendor|provider)",                       ""),
    ("cure_period",            r"cure\s+period\s+of\s+(\d+)\s+days|(\d+)\s+days?\s+to\s+cure",            "days"),
    ("assignment_rights",      r"assign\w*\s+this\s+agreement|assignment\s+of\s+(?:this\s+)?contract",     ""),
]


_SECTION_LABEL_RE = re.compile(
    r"(?m)^(?:"
    r"(?:ARTICLE|SECTION|CLAUSE)\s+(\d+[.\d]*)|"
    r"(\d+\.\d+)\s+[A-Z]|"
    r"(#+ .+)"
    r")"
)


def _section_label_at(text: str, pos: int) -> str:
    """Return the nearest section label before pos, or empty string."""
    candidates = list(_SECTION_LABEL_RE.finditer(text[:pos]))
    if not candidates:
        return ""
    m = candidates[-1]
    return next((g for g in m.groups() if g), "").strip()


def _split_into_sections(text: str, max_size: int = 10_000) -> list[str]:
    """
    Split a large contract into sections for clause extraction.
    Detects common structural headings; falls back to overlapping windows.
    """
    heading_re = re.compile(
        r"(?m)^(?:"
        r"(?:ARTICLE|SECTION|CLAUSE)\s+\d+|"
        r"\d+\.\s{1,4}[A-Z]|"
        r"\d+\.\d+\s+[A-Z]|"
        r"[A-Z][A-Z &\-]{5,}$"
        r")"
    )
    splits = [m.start() for m in heading_re.finditer(text)]

    sections: list[str] = []
    overlap = 500

    if len(splits) >= 3:
        for i, start in enumerate(splits):
            end = splits[i + 1] if i + 1 < len(splits) else len(text)
            chunk = text[start:end]
            if len(chunk) > max_size:
                step = max(1, max_size - overlap)
                for j in range(0, len(chunk), step):
                    sections.append(chunk[j : j + max_size])
            else:
                sections.append(chunk)
    else:
        # No clear headings — sliding window
        step = max(1, max_size - overlap)
        for i in range(0, len(text), step):
            sections.append(text[i : i + max_size])

    return sections


def _extract_clauses_from_section(section: str, seen: set[str]) -> list[dict[str, str]]:
    """Extract clause matches from a single section, deduplicating via shared seen set."""
    findings: list[dict[str, str]] = []
    for clause_type, pattern, unit in _PATTERNS:
        for match in re.finditer(pattern, section, flags=re.IGNORECASE):
            value = next((g for g in match.groups() if g is not None), None) if match.groups() else None
            value = value or match.group(0)
            dedup_key = f"{clause_type}:{value.strip().lower()}"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            span_text = section[max(0, match.start() - _CONTEXT_WINDOW) : match.end() + _CONTEXT_WINDOW]
            section_label = _section_label_at(section, match.start())
            findings.append(
                {
                    "clause_type": clause_type,
                    "extracted_value": f"{value} {unit}".strip(),
                    "source_text": span_text.strip(),
                    "section": section_label,
                }
            )
    return findings


def _extract_clauses(contract_text: str) -> list[dict[str, str]]:
    """Extract clause matches from contract text using regex patterns."""
    sections = (
        _split_into_sections(contract_text)
        if len(contract_text) > _LARGE_CONTRACT_THRESHOLD
        else [contract_text]
    )
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for section in sections:
        out.extend(_extract_clauses_from_section(section, seen))
    return out


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
        value_num = extract_first_number(clause["extracted_value"])

        if value_num is not None and clause["clause_type"] in DEFAULT_RISK_CONFIG:
            risk_level = score_numeric(clause["clause_type"], value_num)

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
        logger.exception("comparison_error", clause_type=clause.get("clause_type"), error=str(exc))
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
        "force_majeure": "Force majeure",
        "warranty": "Warranty period",
        "insurance": "Insurance requirements",
        "change_order": "Change order markup",
        "substantial_completion": "Substantial completion",
        "delay_damages": "Delay damages",
        "governing_law": "Governing law",
        "limitation_of_liability": "Limitation of liability",
        "non_compete": "Non-compete",
        "ip_assignment": "IP assignment",
        "data_privacy": "Data privacy",
        "exclusivity": "Exclusivity",
        "cure_period": "Cure period",
        "assignment_rights": "Assignment rights",
    }
    return labels.get(clause_type, clause_type.replace("_", " ").title())


_REQUIRED_CLAUSE_TYPES: frozenset[str] = frozenset({
    "payment_terms",
    "force_majeure",
    "limitation_of_liability",
    "indemnification",
    "dispute_resolution",
    "termination_notice",
})


_CROSS_REF_PATTERN = re.compile(
    r"notwithstanding\s+(?:Section|Article|Clause)\s+[\d.]+|"
    r"subject\s+to\s+(?:Section|Article|Clause)\s+[\d.]+|"
    r"as\s+provided\s+in\s+(?:Section|Article|Clause)\s+[\d.]+",
    re.IGNORECASE,
)


def detect_cross_references(findings: list[Finding]) -> list[GuardrailWarning]:
    """Flag findings whose source text references other contract sections."""
    warnings: list[GuardrailWarning] = []
    for finding in findings:
        if _CROSS_REF_PATTERN.search(finding.source_text):
            warnings.append(
                GuardrailWarning(
                    type="cross_reference",
                    message=(
                        f"Clause '{finding.clause_type}' references another section — "
                        "review interaction with the referenced clause."
                    ),
                    triggered_by=finding.clause_type,
                )
            )
    return warnings


def detect_missing_clauses(findings: list[Finding]) -> list[GuardrailWarning]:
    """Return a warning for each required clause type absent from findings."""
    found_types = {f.clause_type for f in findings}
    warnings: list[GuardrailWarning] = []
    for clause_type in sorted(_REQUIRED_CLAUSE_TYPES):
        if clause_type not in found_types:
            warnings.append(
                GuardrailWarning(
                    type="missing_clause",
                    message=f"Standard clause '{clause_type}' was not found in the contract.",
                    triggered_by=clause_type,
                )
            )
    return warnings


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


_AMPLIFICATION_PAIRS: list[tuple[str, str]] = [
    ("payment_terms", "retainage"),
    ("liquidated_damages", "delay_damages"),
    ("indemnification", "limitation_of_liability"),
]
_RISK_UPGRADE: dict[str, str] = {
    "low": "medium",
    "medium": "high",
    "high": "critical",
    "critical": "critical",
}


def amplify_inter_clause_risks(findings: list[Finding]) -> list[Finding]:
    """
    Upgrade risk level for findings where two related high-risk clauses are both present.
    e.g. long payment_terms + high retainage compound cash-flow risk.
    """
    risk_map: dict[str, Finding] = {f.clause_type: f for f in findings}
    for ct_a, ct_b in _AMPLIFICATION_PAIRS:
        a = risk_map.get(ct_a)
        b = risk_map.get(ct_b)
        if not a or not b:
            continue
        if _risk_index(a.risk_level) >= _risk_index("high") and _risk_index(b.risk_level) >= _risk_index("high"):
            a.risk_level = _RISK_UPGRADE.get(a.risk_level, a.risk_level)  # type: ignore[assignment]
            b.risk_level = _RISK_UPGRADE.get(b.risk_level, b.risk_level)  # type: ignore[assignment]
    return findings


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


_LLM_CONCURRENCY = 5
_CLAUSE_TIMEOUT_SECS = 45.0


async def _call_llm_for_clause(
    clause: dict[str, str],
    retrieved_chunks: list[RetrievedChunk],
    standard: str,
    deviation: str,
    risk_level: str,
    analysis_type: str,
    llm_client: AnthropicClient,
    semaphore: asyncio.Semaphore,
) -> tuple[Finding, LLMUsage]:
    """Run LLM enrichment for one clause, gated by semaphore. Falls back to heuristic on timeout."""
    async with semaphore:
        citation_ids = _format_citation_ids(retrieved_chunks)
        playbook_ctx = " ".join(chunk.content for chunk in retrieved_chunks)
        usage = LLMUsage(0, 0)

        try:
            if analysis_type == "summary":
                prompt = (
                    f"Clause type: {_friendly_clause_label(clause['clause_type'])}.\n"
                    f"Extracted value: {clause['extracted_value']}.\n"
                    f"Playbook standard: {standard}.\n"
                    f"Detected deviation: {deviation}.\n"
                    f"Source text: {clause['source_text'][:400]}\n\n"
                    f"Summarize this clause for a project manager — plain language, no jargon."
                )
                out, usage = await asyncio.wait_for(  # type: ignore[call-overload]
                    llm_client.summarize_clause(prompt, max_tokens=256, playbook_context=playbook_ctx),
                    timeout=_CLAUSE_TIMEOUT_SECS,
                )
                risk_flag_level = "medium" if out.risk_flag else risk_level
                key_terms_str = "; ".join(out.key_terms) if out.key_terms else clause["extracted_value"]
                finding = Finding(
                    clause_type=clause["clause_type"],
                    extracted_value=key_terms_str,
                    playbook_standard=standard,
                    deviation=deviation,
                    risk_level=risk_flag_level,  # type: ignore[arg-type]
                    recommendation=out.plain_language or f"See playbook reference {citation_ids}",
                    source_text=clause["source_text"],
                    retrieved_chunks=retrieved_chunks,
                    section=clause.get("section") or None,
                )

            elif analysis_type == "obligations":
                prompt = (
                    f"Clause type: {_friendly_clause_label(clause['clause_type'])}.\n"
                    f"Extracted value: {clause['extracted_value']}.\n"
                    f"Playbook standard: {standard}.\n"
                    f"Source text: {clause['source_text'][:400]}\n\n"
                    f"Extract every concrete obligation this clause creates. Be specific and action-oriented."
                )
                oblig_out, usage = await asyncio.wait_for(  # type: ignore[call-overload]
                    llm_client.extract_obligations(prompt, max_tokens=384, playbook_context=playbook_ctx),
                    timeout=_CLAUSE_TIMEOUT_SECS,
                )
                obligations_text = "; ".join(oblig_out.obligations) if oblig_out.obligations else deviation
                deadline_note = f" Deadline: {oblig_out.deadline}." if oblig_out.deadline else ""
                consequence_note = f" Consequence: {oblig_out.consequence}." if oblig_out.consequence else ""
                finding = Finding(
                    clause_type=clause["clause_type"],
                    extracted_value=clause["extracted_value"],
                    playbook_standard=standard,
                    deviation=f"Party: {oblig_out.party}.{deadline_note}{consequence_note}",
                    risk_level=risk_level,  # type: ignore[arg-type]
                    recommendation=f"{obligations_text} (Refs: {citation_ids})",
                    source_text=clause["source_text"],
                    retrieved_chunks=retrieved_chunks,
                    section=clause.get("section") or None,
                )

            else:
                prompt = (
                    f"Clause type: {_friendly_clause_label(clause['clause_type'])}.\n"
                    f"Extracted value: {clause['extracted_value']}.\n"
                    f"Playbook standard: {standard}.\n"
                    f"Heuristic deviation: {deviation}.\n"
                    f"Heuristic risk level: {risk_level}.\n"
                    f"Source text: {clause['source_text'][:400]}"
                )
                risk_out, usage = await asyncio.wait_for(  # type: ignore[call-overload]
                    llm_client.analyze_risk(prompt, max_tokens=512, playbook_context=playbook_ctx),
                    timeout=_CLAUSE_TIMEOUT_SECS,
                )
                final_risk = risk_out.risk_level if risk_out.risk_level != "unknown" else risk_level
                finding = Finding(
                    clause_type=clause["clause_type"],
                    extracted_value=clause["extracted_value"],
                    playbook_standard=standard,
                    deviation=risk_out.deviation_summary or deviation,
                    risk_level=final_risk,  # type: ignore[arg-type]
                    recommendation=f"{risk_out.recommendation} (Playbook refs: {citation_ids})",
                    source_text=clause["source_text"],
                    retrieved_chunks=retrieved_chunks,
                    confidence=risk_out.confidence,
                    section=clause.get("section") or None,
                )

        except asyncio.TimeoutError:
            logger.warning("clause_llm_timeout", clause_type=clause["clause_type"], timeout=_CLAUSE_TIMEOUT_SECS)
            finding = Finding(
                clause_type=clause["clause_type"],
                extracted_value=clause["extracted_value"],
                playbook_standard=standard,
                deviation=deviation,
                risk_level=risk_level,  # type: ignore[arg-type]
                recommendation=f"LLM timed out — heuristic assessment only (refs: {citation_ids})",
                source_text=clause["source_text"],
                retrieved_chunks=retrieved_chunks,
                confidence=0.25,
                section=clause.get("section") or None,
            )

        return finding, usage


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

    log = logger.bind(analysis_id=analysis.id, analysis_type=analysis.analysis_type)
    log.info("pipeline_start", contract_length=len(analysis.contract_text))

    guardrails: list[GuardrailWarning] = list(initial_guardrails or [])
    sanitized_text, extra_warnings = filter_malicious_segments(analysis.contract_text)
    guardrails.extend(extra_warnings)
    analysis.contract_text = sanitized_text
    if session:
        await session.flush()

    # Clause extraction with per-section progress
    _sections = (
        _split_into_sections(sanitized_text)
        if len(sanitized_text) > _LARGE_CONTRACT_THRESHOLD
        else [sanitized_text]
    )
    _total_sections = len(_sections)
    _seen: set[str] = set()
    extracted_clauses: list[dict[str, str]] = []
    for _i, _section in enumerate(_sections):
        extracted_clauses.extend(_extract_clauses_from_section(_section, _seen))
        await _emit(
            "status",
            {
                "analysis_id": analysis.id,
                "status": "extracting",
                "message": f"Scanning section {_i + 1}/{_total_sections}",
                "progress": round((_i + 1) / _total_sections * 100),
            },
        )

    # Determine playbook version
    version_id = analysis.playbook_version_id
    if playbook_content_override:
        version_id = "in-memory"
    if not version_id and session:
        db_result = await session.execute(
            select(PlaybookVersion)
            .where(PlaybookVersion.deleted_at.is_(None))
            .order_by(PlaybookVersion.created_at.desc())
        )
        latest = db_result.scalars().first()
        if latest:
            version_id = latest.id
            analysis.playbook_version_id = version_id

    rag = PlaybookRAG()
    if playbook_content_override:
        chunks = chunk_playbook(playbook_content_override)
        vid: str = version_id or "in-memory"
        await rag.reset_version(vid, [(f"{vid}-{idx}", text) for idx, text in enumerate(chunks)])
    findings: list[Finding] = []
    llm_client = AnthropicClient()
    total_usage = LLMUsage(0, 0)

    # Pass 1 — heuristic-score every extracted clause (no LLM, fast)
    _ScoredClause = tuple  # (clause, retrieved_chunks, standard, deviation, risk_level)
    scored: list[tuple[dict[str, str], list[RetrievedChunk], str, str, str]] = []
    for clause in extracted_clauses:
        retrieved: list[RetrievedChunk] = await rag.hybrid_query(version_id, clause["source_text"]) if version_id else []
        if not retrieved:
            continue
        standard, deviation, risk_level = _compare_with_playbook(clause, retrieved)
        scored.append((clause, retrieved, standard, deviation, risk_level))

    # Sort highest-risk first; only top _MAX_LLM_FINDINGS go to the LLM
    scored.sort(key=lambda x: _risk_index(x[4]), reverse=True)
    llm_batch = scored[:_MAX_LLM_FINDINGS]
    heuristic_only = scored[_MAX_LLM_FINDINGS:]

    await _emit(
        "status",
        {
            "analysis_id": analysis.id,
            "status": "analyzing",
            "message": (
                f"LLM analysis for {len(llm_batch)} clause(s)"
                + (f"; {len(heuristic_only)} assessed heuristically" if heuristic_only else "")
            ),
        },
    )

    # Emit heuristic-only findings immediately (no LLM cost)
    for clause, retrieved_chunks, standard, deviation, risk_level in heuristic_only:
        citation_ids = _format_citation_ids(retrieved_chunks)
        finding = Finding(
            clause_type=clause["clause_type"],
            extracted_value=clause["extracted_value"],
            playbook_standard=standard,
            deviation=deviation,
            risk_level=risk_level,  # type: ignore[arg-type]
            recommendation=f"Heuristic assessment (low priority — see playbook refs {citation_ids})",
            source_text=clause["source_text"],
            retrieved_chunks=retrieved_chunks,
            confidence=0.3,
            section=clause.get("section") or None,
        )
        findings.append(finding)
        await _emit("partial_finding", {"analysis_id": analysis.id, "finding": finding.dict()})

    # Pass 2 — concurrent LLM enrichment for top _MAX_LLM_FINDINGS clauses
    semaphore = asyncio.Semaphore(_LLM_CONCURRENCY)
    llm_tasks = [
        _call_llm_for_clause(clause, chunks, std, dev, risk, analysis.analysis_type, llm_client, semaphore)
        for clause, chunks, std, dev, risk in llm_batch
    ]
    for coro in asyncio.as_completed(llm_tasks):
        finding, usage = await coro
        total_usage.input_tokens += usage.input_tokens
        total_usage.output_tokens += usage.output_tokens
        findings.append(finding)
        await _emit("partial_finding", {"analysis_id": analysis.id, "finding": finding.dict()})

    # Drop invalid findings (missing source or retrieval)
    merged_findings = amplify_inter_clause_risks(_merge_findings(findings))
    guardrails.extend(ensure_retrieval_guardrails([f.dict() for f in merged_findings]))
    merged_findings = [
        f
        for f in merged_findings
        if f.source_text
        and f.retrieved_chunks
    ]

    missing_warnings = detect_missing_clauses(merged_findings)
    guardrails.extend(missing_warnings)
    cross_ref_warnings = detect_cross_references(merged_findings)
    guardrails.extend(cross_ref_warnings)

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

    log.info(
        "pipeline_complete",
        finding_count=len(merged_findings),
        overall_risk=overall,
        input_tokens=total_usage.input_tokens,
        output_tokens=total_usage.output_tokens,
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
