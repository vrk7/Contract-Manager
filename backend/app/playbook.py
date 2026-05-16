from __future__ import annotations

import re
from pathlib import Path

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import PlaybookChunk, PlaybookVersion
from .rag import PlaybookRAG, chunk_playbook_with_headings
from .schemas import PlaybookResponse

logger = structlog.get_logger(__name__)

_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)


def _extract_section_headings(content: str) -> list[tuple[int, str]]:
    """Return (char_offset, heading_text) pairs for all markdown headings."""
    return [(m.start(), m.group(0).strip()) for m in _HEADING_RE.finditer(content)]


def _heading_for_offset(offset: int, headings: list[tuple[int, str]]) -> str | None:
    """Return the most recent heading before the given character offset."""
    current: str | None = None
    for pos, heading in headings:
        if pos <= offset:
            current = heading
        else:
            break
    return current


async def seed_playbook(session: AsyncSession, seed_path: str) -> PlaybookVersion:
    existing_result = await session.execute(
        select(PlaybookVersion)
        .where(PlaybookVersion.deleted_at.is_(None))
        .order_by(PlaybookVersion.created_at.desc())
    )
    existing_version = existing_result.scalars().first()
    if existing_version:
        # Ensure embeddings exist even if Chroma storage was lost between deployments.
        rag = PlaybookRAG()
        collection_count = rag.collection_count(existing_version.id)
        chunk_result = await session.execute(
            select(PlaybookChunk).where(PlaybookChunk.version_id == existing_version.id)
        )
        chunks = chunk_result.scalars().all()
        if collection_count == 0:
            if chunks:
                rag.reset_version(existing_version.id, [(c.id, c.content) for c in chunks])
            else:
                await persist_chunks(session, existing_version.id, existing_version.content)
            logger.info("playbook_embeddings_rebuilt", version_id=existing_version.id)
        return existing_version
    content = Path(seed_path).read_text(encoding="utf-8")
    version = PlaybookVersion(content=content, change_note="Initial seed", version_label="1.0")
    session.add(version)
    await session.flush()
    await persist_chunks(session, version.id, content)
    return version


async def persist_chunks(session: AsyncSession, version_id: str, content: str) -> None:
    await session.execute(delete(PlaybookChunk).where(PlaybookChunk.version_id == version_id))
    raw_chunks = chunk_playbook_with_headings(content)
    headings = _extract_section_headings(content)
    rag = PlaybookRAG()
    chunk_records: list[PlaybookChunk] = []
    search_offset = 0
    for idx, text in enumerate(raw_chunks):
        # Locate this chunk in the original content to find its heading context.
        pos = content.find(text[:40], search_offset)
        if pos == -1:
            pos = search_offset
        else:
            search_offset = pos + len(text)
        heading = _heading_for_offset(pos, headings)
        # chunk_playbook_with_headings already prepends [Section: ...] but we
        # keep the fallback here for any chunks that didn't get a heading injected.
        embedded_text = text if text.startswith("[Section:") else (f"{heading}\n\n{text}" if heading else text)
        chunk_id = f"{version_id}-{idx}"
        chunk_records.append(
            PlaybookChunk(
                id=chunk_id,
                version_id=version_id,
                content=embedded_text,
                source="standard_terms_playbook.md",
            )
        )
    session.add_all(chunk_records)
    await session.flush()
    rag.reset_version(version_id, [(c.id, c.content) for c in chunk_records])


async def list_playbook_versions(session: AsyncSession) -> list[PlaybookResponse]:
    result = await session.execute(
        select(PlaybookVersion)
        .where(PlaybookVersion.deleted_at.is_(None))
        .order_by(PlaybookVersion.created_at.desc())
    )
    return [
        PlaybookResponse(
            id=row.id,
            created_at=row.created_at,
            content=row.content,
            change_note=row.change_note,
            version_label=row.version_label,
        )
        for row in result.scalars().all()
    ]
