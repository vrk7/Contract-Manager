from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import JSON, Column, DateTime, ForeignKey, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def default_uuid() -> str:
    return str(uuid.uuid4())


class PlaybookVersion(Base):
    __tablename__ = "playbook_versions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=default_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    change_note: Mapped[str | None] = mapped_column(String, nullable=True)
    version_label: Mapped[str | None] = mapped_column(String, nullable=True)

    chunks: Mapped[list["PlaybookChunk"]] = relationship(
        "PlaybookChunk", back_populates="version", cascade="all, delete-orphan"
    )


class PlaybookChunk(Base):
    __tablename__ = "playbook_chunks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=default_uuid)
    version_id: Mapped[str] = mapped_column(
        String, ForeignKey("playbook_versions.id"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String, default="playbook")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    version: Mapped[PlaybookVersion] = relationship("PlaybookVersion", back_populates="chunks")


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=default_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    analysis_type: Mapped[str] = mapped_column(String, nullable=False)
    contract_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, default="queued")
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    playbook_version_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("playbook_versions.id"), nullable=True
    )
    guardrail_warnings: Mapped[str | None] = mapped_column(Text, nullable=True)
    usage_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    version: Mapped[PlaybookVersion | None] = relationship("PlaybookVersion")

    @staticmethod
    def _json_serializer(obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, BaseModel):
            return obj.dict()
        if hasattr(obj, "dict"):
            return obj.dict()
        return str(obj)

    def set_result(self, result: Any) -> None:
        if isinstance(result, BaseModel):
            self.result_json = result.json()
        else:
            self.result_json = json.dumps(result, default=self._json_serializer)

    def set_usage(self, usage: Any) -> None:
        self.usage_json = json.dumps(usage, default=self._json_serializer)

    def set_guardrails(self, warnings: Any) -> None:
        self.guardrail_warnings = json.dumps(warnings, default=self._json_serializer)