import asyncio
import json
import logging
from datetime import datetime
from typing import Any
from pathlib import Path
import uuid

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .database import Base, engine, get_session
from .events import event_bus
from .guards import filter_malicious_segments
from .models import Analysis, PlaybookVersion
from .pipeline import run_analysis_pipeline
from .playbook import list_playbook_versions, persist_chunks, seed_playbook
from .schemas import (
    AnalysisCreateRequest,
    AnalysisResult,
    AnalysisStatusResponse,
    GuardrailWarning,
    PlaybookReindexRequest,
    PlaybookResponse,
    PlaybookUpdateRequest,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_settings()
IN_MEMORY_RESULTS: dict[str, dict] = {}

limiter = Limiter(key_func=get_remote_address, default_limits=[f"{settings.rate_limit_per_minute}/minute"])
app = FastAPI(title=settings.app_name)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["meta"])
async def root() -> dict[str, str]:
    """Provide a simple landing response instead of a 404 on the root path."""
    return {
        "status": "ok",
        "message": "Backend is running. Visit /health for a probe or /docs for the API schema.",
    }


@app.on_event("startup")
async def startup_event() -> None:
    if settings.in_memory_mode:
        return
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with get_session() as session:
        await seed_playbook(session, str(settings.resolve_playbook_path()))


async def session_dependency():
    if settings.in_memory_mode:
        yield None
    else:
        async with get_session() as session:
            yield session


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


async def _process_analysis(analysis_id: str) -> None:
    async with get_session() as session:
        result = await session.execute(select(Analysis).where(Analysis.id == analysis_id))
        analysis = result.scalars().first()
        if not analysis:
            return

        async def streamer(event: str, data: Any) -> None:
            event_bus.publish(analysis.id, event, data)

        try:
            event_bus.publish(analysis.id, "status", {"analysis_id": analysis.id, "status": "running", "message": "Started analysis"})
            initial_guardrails = []
            if analysis.guardrail_warnings:
                try:
                    initial_guardrails = [GuardrailWarning(**w) for w in json.loads(analysis.guardrail_warnings)]
                except Exception:
                    initial_guardrails = []
            pipeline_result = await run_analysis_pipeline(
                session, analysis, streamer=streamer, initial_guardrails=initial_guardrails
            )
            analysis.status = "completed"
            serialized_result = json.loads(pipeline_result.json())
            analysis.set_result(serialized_result)
            if pipeline_result.guardrail_warnings:
                analysis.set_guardrails([w.dict() for w in pipeline_result.guardrail_warnings])
            if pipeline_result.usage:
                analysis.set_usage(pipeline_result.usage.dict())
            await session.flush()
            event_bus.publish(
                analysis.id,
                "final",
                {"analysis_id": analysis.id, "result": serialized_result},
            )
        except Exception as exc:
            logger.exception("Analysis failed: %s", exc)
            analysis.status = "failed"
            await session.flush()
            event_bus.publish(
                analysis.id,
                "error",
                {"analysis_id": analysis.id, "error": str(exc)},
            )


@app.post("/analyze", response_model=AnalysisStatusResponse)
@limiter.limit(f"{settings.rate_limit_per_minute}/minute")
async def analyze(request: Request, payload: AnalysisCreateRequest, background_tasks: BackgroundTasks, session: AsyncSession | None = Depends(session_dependency)) -> AnalysisStatusResponse:
    contract_text, guardrails = filter_malicious_segments(payload.contract_text)
    if settings.in_memory_mode:
        analysis_id = str(uuid.uuid4())
        fake_analysis = Analysis(
            id=analysis_id,
            analysis_type=payload.analysis_type,
            contract_text=contract_text,
            status="queued",
            playbook_version_id="in-memory",
            guardrail_warnings=json.dumps([g.dict() for g in guardrails]) if guardrails else None,
        )
        playbook_content = settings.resolve_playbook_path().read_text(encoding="utf-8")
        result = await run_analysis_pipeline(
            None,
            fake_analysis,
            playbook_content_override=playbook_content,
            initial_guardrails=guardrails,
        )
        fake_analysis.status = "completed"
        IN_MEMORY_RESULTS[analysis_id] = json.loads(result.json())
        return AnalysisStatusResponse(analysis_id=analysis_id, status="completed")

    analysis = Analysis(
        analysis_type=payload.analysis_type,
        contract_text=contract_text,
        status="queued",
        playbook_version_id=payload.playbook_version_id,
        guardrail_warnings=json.dumps([g.dict() for g in guardrails]) if guardrails else None,
    )
    session.add(analysis)
    await session.flush()
    if settings.inline_analysis:
        result = await run_analysis_pipeline(session, analysis, initial_guardrails=guardrails)
        analysis.status = "completed"
        serialized_result = json.loads(result.json())
        analysis.set_result(serialized_result)
        if result.guardrail_warnings:
            analysis.set_guardrails([g.dict() for g in result.guardrail_warnings])
        if result.usage:
            analysis.set_usage(result.usage.dict())
        await session.flush()
        return AnalysisStatusResponse(analysis_id=analysis.id, status=analysis.status)

    background_tasks.add_task(_process_analysis, analysis.id)
    return AnalysisStatusResponse(analysis_id=analysis.id, status=analysis.status)


@app.get("/analysis/{analysis_id}", response_model=AnalysisResult | AnalysisStatusResponse)
async def get_analysis(analysis_id: str, session: AsyncSession | None = Depends(session_dependency)):
    if settings.in_memory_mode:
        data = IN_MEMORY_RESULTS.get(analysis_id)
        if not data:
            raise HTTPException(status_code=404, detail="Analysis not found")
        return AnalysisResult(**data)

    result = await session.execute(select(Analysis).where(Analysis.id == analysis_id))
    analysis = result.scalars().first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if analysis.result_json:
        result_data = json.loads(analysis.result_json)
        return AnalysisResult(**result_data)
    return AnalysisStatusResponse(analysis_id=analysis.id, status=analysis.status)


def _format_sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.get("/analysis/{analysis_id}/stream")
@limiter.limit(f"{settings.rate_limit_stream_per_minute}/minute")
async def stream_analysis(request: Request, analysis_id: str):  # noqa: ARG001
    if settings.in_memory_mode:
        data = IN_MEMORY_RESULTS.get(analysis_id)
        if not data:
            raise HTTPException(status_code=404, detail="Analysis not found")

        async def immediate():
            yield _format_sse("final", {"analysis_id": analysis_id, "result": data})

        return StreamingResponse(immediate(), media_type="text/event-stream")

    async def event_generator():
        async for item in event_bus.subscribe(analysis_id):
            yield _format_sse(item["event"], item["data"])
    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/playbook", response_model=PlaybookResponse)
async def get_current_playbook(session: AsyncSession | None = Depends(session_dependency)):
    if settings.in_memory_mode:
        content = settings.resolve_playbook_path().read_text(encoding="utf-8")
        return PlaybookResponse(
            id="in-memory",
            created_at=datetime.utcnow(),
            content=content,
            change_note="in-memory",
            version_label="in-memory",
        )

    result = await session.execute(
        select(PlaybookVersion).order_by(PlaybookVersion.created_at.desc())
    )
    version = result.scalars().first()
    if not version:
        raise HTTPException(status_code=404, detail="No playbook version found")
    return PlaybookResponse(
        id=version.id,
        created_at=version.created_at,
        content=version.content,
        change_note=version.change_note,
        version_label=version.version_label,
    )


@app.get("/playbook/versions", response_model=list[PlaybookResponse])
async def get_playbook_versions(session: AsyncSession | None = Depends(session_dependency)):
    if settings.in_memory_mode:
        content = settings.resolve_playbook_path().read_text(encoding="utf-8")
        return [
            PlaybookResponse(
                id="in-memory",
                created_at=datetime.utcnow(),
                content=content,
                change_note="in-memory",
                version_label="in-memory",
            )
        ]
    return await list_playbook_versions(session)


@app.get("/playbook/versions/{version_id}", response_model=PlaybookResponse)
async def get_playbook_version(version_id: str, session: AsyncSession | None = Depends(session_dependency)):
    if settings.in_memory_mode:
        content = settings.resolve_playbook_path().read_text(encoding="utf-8")
        return PlaybookResponse(
            id="in-memory",
            created_at=datetime.utcnow(),
            content=content,
            change_note="in-memory",
            version_label="in-memory",
        )
    result = await session.execute(select(PlaybookVersion).where(PlaybookVersion.id == version_id))
    version = result.scalars().first()
    if not version:
        raise HTTPException(status_code=404, detail="Playbook version not found")
    return PlaybookResponse(
        id=version.id,
        created_at=version.created_at,
        content=version.content,
        change_note=version.change_note,
        version_label=version.version_label,
    )


@app.put("/playbook", response_model=PlaybookResponse)
async def update_playbook(request: PlaybookUpdateRequest, session: AsyncSession | None = Depends(session_dependency)):
    if settings.in_memory_mode:
        return PlaybookResponse(
            id="in-memory",
            created_at=datetime.utcnow(),
            content=request.content,
            change_note=request.change_note,
            version_label="in-memory",
        )
    version = PlaybookVersion(content=request.content, change_note=request.change_note, version_label=datetime.utcnow().strftime("%Y-%m-%d"))
    session.add(version)
    await session.flush()
    await persist_chunks(session, version.id, request.content)
    return PlaybookResponse(
        id=version.id,
        created_at=version.created_at,
        content=version.content,
        change_note=version.change_note,
        version_label=version.version_label,
    )


@app.post("/playbook/reindex")
async def reindex_playbook(body: PlaybookReindexRequest, session: AsyncSession | None = Depends(session_dependency)):
    if settings.in_memory_mode:
        return {"status": "ok", "version_id": "in-memory"}
    version_id = body.version_id
    if not version_id:
        result = await session.execute(
            select(PlaybookVersion).order_by(PlaybookVersion.created_at.desc())
        )
        version = result.scalars().first()
    else:
        result = await session.execute(select(PlaybookVersion).where(PlaybookVersion.id == version_id))
        version = result.scalars().first()
    if not version:
        raise HTTPException(status_code=404, detail="Playbook version not found")
    await persist_chunks(session, version.id, version.content)
    return {"status": "ok", "version_id": version.id}
