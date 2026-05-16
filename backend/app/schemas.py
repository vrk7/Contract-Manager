from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, validator


class GuardrailWarning(BaseModel):
    type: str
    message: str
    triggered_by: str | None = None


class RetrievedChunk(BaseModel):
    chunk_id: str
    content: str
    source: str
    playbook_version_id: str


class Finding(BaseModel):
    clause_type: str
    extracted_value: str
    playbook_standard: str
    deviation: str
    risk_level: Literal["critical", "high", "medium", "low", "acceptable", "unknown"]
    recommendation: str
    source_text: str
    retrieved_chunks: list[RetrievedChunk] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    section: Optional[str] = None


class Usage(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float


class AnalysisResult(BaseModel):
    analysis_id: str
    timestamp: datetime
    overall_risk_score: Literal["critical", "high", "medium", "low", "acceptable", "unknown"]
    findings: list[Finding]
    guardrail_warnings: list[GuardrailWarning] = Field(default_factory=list)
    confidence_score: float
    playbook_version_id: Optional[str] = None
    usage: Optional[Usage] = None


class AnalysisCreateRequest(BaseModel):
    contract_text: str = Field(min_length=10, max_length=5_000_000)
    analysis_type: Literal["risks", "summary", "obligations"]
    playbook_version_id: Optional[str] = None

    @validator("contract_text")
    def normalize_text(cls, v: str) -> str:
        v = v.strip()
        if not v.isprintable() and len([c for c in v if ord(c) < 32 and c not in "\t\n\r"]) > len(v) * 0.1:
            raise ValueError("Contract text appears to contain binary or non-text content")
        return v


class AnalysisStatusResponse(BaseModel):
    analysis_id: str
    status: str


class PlaybookUpdateRequest(BaseModel):
    content: str
    change_note: Optional[str] = None


class PlaybookResponse(BaseModel):
    id: str
    created_at: datetime
    content: str
    change_note: Optional[str] = None
    version_label: Optional[str] = None


class PlaybookVersionList(BaseModel):
    versions: list[PlaybookResponse]


class PlaybookReindexRequest(BaseModel):
    version_id: Optional[str] = None


class AnalysisListItem(BaseModel):
    analysis_id: str
    status: str
    analysis_type: str
    created_at: datetime
    overall_risk_score: Optional[str] = None


class AnalysisListResponse(BaseModel):
    items: list[AnalysisListItem]
    next_cursor: Optional[str] = None
    total: int


class LLMFindingOutput(BaseModel):
    """Structured output from Claude for risks analysis (via tool_use)."""

    risk_level: Literal["critical", "high", "medium", "low", "acceptable", "unknown"] = "medium"
    deviation_summary: str = ""
    recommendation: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class LLMSummaryOutput(BaseModel):
    """Structured output from Claude for summary analysis (via tool_use)."""

    plain_language: str = ""
    key_terms: list[str] = Field(default_factory=list)
    risk_flag: bool = False


class LLMObligationOutput(BaseModel):
    """Structured output from Claude for obligations analysis (via tool_use)."""

    obligations: list[str] = Field(default_factory=list)
    party: str = "contractor"
    deadline: Optional[str] = None
    consequence: Optional[str] = None


# ── Auth schemas ─────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    email: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    email: str
    created_at: datetime
