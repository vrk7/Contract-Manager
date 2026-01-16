from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import PlaybookChunk, PlaybookVersion
from .rag import PlaybookRAG, chunk_playbook
from .schemas import PlaybookResponse

logger = logging.getLogger(__name__)


async def seed_playbook(session: AsyncSession, seed_path: str) -> PlaybookVersion:
    existing_result = await session.execute(select(PlaybookVersion).order_by(PlaybookVersion.created_at.desc()))
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
            logger.info("Rebuilt playbook embeddings for version %s", existing_version.id)
        return existing_version
    content = Path(seed_path).read_text(encoding="utf-8")
    version = PlaybookVersion(content=content, change_note="Initial seed", version_label="1.0")
    session.add(version)
    await session.flush()
    await persist_chunks(session, version.id, content)
    return version


async def persist_chunks(session: AsyncSession, version_id: str, content: str) -> None:
    # remove existing
    await session.execute(delete(PlaybookChunk).where(PlaybookChunk.version_id == version_id))
    chunks = chunk_playbook(content)
    rag = PlaybookRAG()
    chunk_records: list[PlaybookChunk] = []
    for idx, text in enumerate(chunks):
        chunk_id = f"{version_id}-{idx}"
        chunk_records.append(
            PlaybookChunk(
                id=chunk_id,
                version_id=version_id,
                content=text,
                source="standard_terms_playbook.md",
            )
        )
    session.add_all(chunk_records)
    await session.flush()
    rag.reset_version(version_id, [(c.id, c.content) for c in chunk_records])


async def list_playbook_versions(session: AsyncSession) -> list[PlaybookResponse]:
    result = await session.execute(
        select(PlaybookVersion).order_by(PlaybookVersion.created_at.desc())
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
