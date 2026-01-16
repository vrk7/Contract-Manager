from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl, validator


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
    contract_text: str = Field(min_length=10)
    analysis_type: Literal["risks", "summary", "obligations"]
    playbook_version_id: Optional[str] = None

    @validator("contract_text")
    def normalize_text(cls, v: str) -> str:
        return v.strip()


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
