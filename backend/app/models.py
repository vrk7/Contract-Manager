from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Boolean, DateTime, ForeignKey, LargeBinary, String, Text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def default_uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=default_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    analyses: Mapped[list["Analysis"]] = relationship("Analysis", back_populates="user")


class PlaybookVersion(Base):
    __tablename__ = "playbook_versions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=default_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    change_note: Mapped[str | None] = mapped_column(String, nullable=True)
    version_label: Mapped[str | None] = mapped_column(String, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

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
    request_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True, index=True)

    version: Mapped[PlaybookVersion | None] = relationship("PlaybookVersion")
    user: Mapped["User | None"] = relationship("User", back_populates="analyses")

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


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=default_uuid)
    table_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    row_id: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    changed_by: Mapped[str | None] = mapped_column(String, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    diff_json: Mapped[str | None] = mapped_column(Text, nullable=True)


async def write_audit_log(
    session: AsyncSession,
    table_name: str,
    row_id: str,
    action: str,
    changed_by: str | None = None,
    diff: dict | None = None,
) -> None:
    entry = AuditLog(
        table_name=table_name,
        row_id=row_id,
        action=action,
        changed_by=changed_by,
        diff_json=json.dumps(diff) if diff else None,
    )
    session.add(entry)
