import asyncio
import json
import os
import uuid
from datetime import datetime
from typing import Any

import structlog
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import StreamingResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import (
    create_access_token,
    get_current_user_id,
    get_current_user_id_from_query,
    hash_password,
    verify_password,
)
from .cache import AnalysisCache, analysis_cache
from .config import get_settings
from .database import get_session
from .events import event_bus
from .guards import filter_malicious_segments
from .logging_config import configure_logging
from .middleware import RequestTimingMiddleware
from .models import Analysis, PlaybookVersion, User, write_audit_log
from .pipeline import run_analysis_pipeline
from .playbook import list_playbook_versions, persist_chunks, seed_playbook
from .schemas import (
    AnalysisCreateRequest,
    AnalysisListItem,
    AnalysisListResponse,
    AnalysisResult,
    AnalysisStatusResponse,
    GuardrailWarning,
    PlaybookReindexRequest,
    PlaybookResponse,
    PlaybookUpdateRequest,
    Token,
    UserCreate,
    UserLogin,
    UserResponse,
)

configure_logging()
logger = structlog.get_logger(__name__)
settings = get_settings()
IN_MEMORY_RESULTS: dict[str, dict] = {}


limiter = Limiter(key_func=get_remote_address, default_limits=[f"{settings.rate_limit_per_minute}/minute"])
app = FastAPI(title=settings.app_name)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

v1 = APIRouter(prefix="/v1")

app.add_middleware(RequestTimingMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1024)
_cors_origins = (
    [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
    or ([] if settings.production_mode else ["http://localhost:5173", "http://localhost:3000"])
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins if _cors_origins else ["http://localhost:5173"],
    allow_credentials=not settings.production_mode,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID", "Idempotency-Key"],
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none';"
    )
    if settings.production_mode:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    return response


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    import structlog.contextvars as _ctxvars
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    _ctxvars.clear_contextvars()
    _ctxvars.bind_contextvars(request_id=request_id)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/", tags=["meta"])
async def root() -> dict[str, str]:
    """Provide a simple landing response instead of a 404 on the root path."""
    return {
        "status": "ok",
        "message": "Backend is running. Visit /health for a probe or /docs for the API schema.",
    }


@app.on_event("shutdown")
async def shutdown_event() -> None:
    logger.info("shutdown_started", message="Draining in-flight requests before exit")
    await asyncio.sleep(0.5)
    logger.info("shutdown_complete")


@app.on_event("startup")
async def startup_event() -> None:
    if settings.in_memory_mode:
        return
    # Schema is managed by Alembic. Run `alembic upgrade head` before starting
    # the app for the first time or after any schema change.
    async with get_session() as session:
        await seed_playbook(session, str(settings.resolve_playbook_path()))


async def session_dependency():
    if settings.in_memory_mode:
        yield None
    else:
        async with get_session() as session:
            yield session


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok"}


@app.get("/health/deep")
async def health_deep() -> dict[str, Any]:
    """Deep health check — verifies DB connectivity and Chroma availability."""
    checks: dict[str, str] = {}

    if not settings.in_memory_mode:
        try:
            async with get_session() as session:
                await session.execute(select(Analysis).limit(1))
            checks["database"] = "ok"
        except Exception as exc:
            checks["database"] = f"error: {exc}"
    else:
        checks["database"] = "in-memory"

    try:
        from .rag import get_chroma_client
        client = get_chroma_client()
        client.list_collections()
        checks["chroma"] = "ok"
    except Exception as exc:
        checks["chroma"] = f"error: {exc}"

    checks["llm_key"] = "configured" if settings.anthropic_api_key else "missing"

    overall = "ok" if all(v in ("ok", "in-memory", "configured") for v in checks.values()) else "degraded"
    return {"status": overall, "checks": checks}


_PIPELINE_TIMEOUT_SECS = 600.0


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
            pipeline_result = await asyncio.wait_for(
                run_analysis_pipeline(session, analysis, streamer=streamer, initial_guardrails=initial_guardrails),
                timeout=_PIPELINE_TIMEOUT_SECS,
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
        except asyncio.TimeoutError:
            logger.error("analysis_timeout", analysis_id=analysis_id, timeout=_PIPELINE_TIMEOUT_SECS)
            analysis.status = "failed"
            await session.flush()
            event_bus.publish(
                analysis.id,
                "error",
                {"analysis_id": analysis.id, "error": "Analysis timed out after 10 minutes. Try a shorter contract."},
            )
        except Exception as exc:
            logger.exception("analysis_failed", error=str(exc))
            analysis.status = "failed"
            await session.flush()
            event_bus.publish(
                analysis.id,
                "error",
                {"analysis_id": analysis.id, "error": str(exc)},
            )


@v1.post("/analyze", response_model=AnalysisStatusResponse)
@limiter.limit(f"{settings.rate_limit_per_minute}/minute")
async def analyze(request: Request, payload: AnalysisCreateRequest, background_tasks: BackgroundTasks, session: AsyncSession | None = Depends(session_dependency), current_user_id: str | None = Depends(get_current_user_id)) -> AnalysisStatusResponse:
    user_ip = request.client.host if request.client else "unknown"
    request_id = getattr(request.state, "request_id", "unknown")
    idempotency_key: str | None = request.headers.get("Idempotency-Key")
    logger.info("analyze_request", user_ip=user_ip, request_id=request_id, analysis_type=payload.analysis_type)

    cache_key = AnalysisCache.make_key(
        payload.contract_text,
        payload.playbook_version_id or "latest",
        payload.analysis_type,
    )
    cached = analysis_cache.get(cache_key)
    if cached:
        logger.info("cache_hit", cache_key=cache_key[:16])
        return AnalysisStatusResponse(analysis_id=cached["analysis_id"], status="completed")

    if idempotency_key and session and not settings.in_memory_mode:
        existing = await session.execute(
            select(Analysis).where(Analysis.request_id == idempotency_key, Analysis.deleted_at.is_(None))
        )
        dup = existing.scalars().first()
        if dup:
            logger.info("idempotency_hit", idempotency_key=idempotency_key, analysis_id=dup.id)
            return AnalysisStatusResponse(analysis_id=dup.id, status=dup.status)

    contract_text, guardrails = filter_malicious_segments(payload.contract_text)
    if settings.in_memory_mode:
        analysis_id = str(uuid.uuid4())
        fake_analysis = Analysis(
            id=analysis_id,
            analysis_type=payload.analysis_type,
            contract_text=contract_text,
            status="queued",
            playbook_version_id="in-memory",
            request_id=request_id,
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

    assert session is not None
    analysis = Analysis(
        analysis_type=payload.analysis_type,
        contract_text=contract_text,
        status="queued",
        playbook_version_id=payload.playbook_version_id,
        request_id=idempotency_key or request_id,
        guardrail_warnings=json.dumps([g.dict() for g in guardrails]) if guardrails else None,
        user_id=current_user_id,
    )
    session.add(analysis)
    await session.flush()
    await write_audit_log(session, "analyses", analysis.id, "create", changed_by=user_ip)
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

    await session.commit()
    background_tasks.add_task(_process_analysis, analysis.id)
    return AnalysisStatusResponse(analysis_id=analysis.id, status=analysis.status)


@v1.get("/analyses", response_model=AnalysisListResponse)
async def list_analyses(
    status: str | None = Query(default=None),
    analysis_type: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession | None = Depends(session_dependency),
    _uid: str | None = Depends(get_current_user_id),
) -> AnalysisListResponse:
    if settings.in_memory_mode:
        return AnalysisListResponse(items=[], next_cursor=None, total=0)

    assert session is not None
    query = select(Analysis).where(Analysis.deleted_at.is_(None))
    if status:
        query = query.where(Analysis.status == status)
    if analysis_type:
        query = query.where(Analysis.analysis_type == analysis_type)
    if cursor:
        query = query.where(Analysis.created_at < cursor)
    query = query.order_by(Analysis.created_at.desc()).limit(limit + 1)

    db_result = await session.execute(query)
    rows = db_result.scalars().all()

    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = str(page[-1].created_at) if has_more and page else None

    items = []
    for row in page:
        overall = None
        if row.result_json:
            try:
                overall = json.loads(row.result_json).get("overall_risk_score")
            except Exception:
                pass
        items.append(AnalysisListItem(
            analysis_id=row.id,
            status=row.status,
            analysis_type=row.analysis_type,
            created_at=row.created_at,
            overall_risk_score=overall,
        ))

    count_query = select(func.count()).select_from(Analysis).where(Analysis.deleted_at.is_(None))
    if status:
        count_query = count_query.where(Analysis.status == status)
    if analysis_type:
        count_query = count_query.where(Analysis.analysis_type == analysis_type)
    count_result = await session.execute(count_query)
    total = count_result.scalar_one()

    return AnalysisListResponse(items=items, next_cursor=next_cursor, total=total)


@v1.get("/analysis/{analysis_id}", response_model=AnalysisResult | AnalysisStatusResponse)
async def get_analysis(analysis_id: str, request: Request, session: AsyncSession | None = Depends(session_dependency), _uid: str | None = Depends(get_current_user_id)):
    if settings.in_memory_mode:
        data = IN_MEMORY_RESULTS.get(analysis_id)
        if not data:
            raise HTTPException(status_code=404, detail="Analysis not found")
        return AnalysisResult(**data)

    assert session is not None
    result = await session.execute(
        select(Analysis).where(Analysis.id == analysis_id, Analysis.deleted_at.is_(None))
    )
    analysis = result.scalars().first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if analysis.result_json:
        import hashlib as _hl
        etag = _hl.md5(analysis.result_json.encode(), usedforsecurity=False).hexdigest()
        if request.headers.get("If-None-Match") == etag:
            from fastapi.responses import Response as _Resp
            return _Resp(status_code=304, headers={"ETag": etag})
        from fastapi.responses import JSONResponse as _JSON
        result_data = json.loads(analysis.result_json)
        return _JSON(content=result_data, headers={"ETag": etag})
    return AnalysisStatusResponse(analysis_id=analysis.id, status=analysis.status)


def _format_sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@v1.delete("/analysis/{analysis_id}", status_code=204)
async def delete_analysis(analysis_id: str, session: AsyncSession | None = Depends(session_dependency), _uid: str | None = Depends(get_current_user_id)):
    """Soft-delete an analysis by setting deleted_at."""
    if settings.in_memory_mode:
        IN_MEMORY_RESULTS.pop(analysis_id, None)
        return

    assert session is not None
    result = await session.execute(
        select(Analysis).where(Analysis.id == analysis_id, Analysis.deleted_at.is_(None))
    )
    analysis = result.scalars().first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    analysis.deleted_at = datetime.utcnow()
    await write_audit_log(session, "analyses", analysis_id, "delete")
    await session.flush()


@v1.get("/analysis/{analysis_id}/stream")
@limiter.limit(f"{settings.rate_limit_stream_per_minute}/minute")
async def stream_analysis(request: Request, analysis_id: str, _uid: str | None = Depends(get_current_user_id_from_query)):  # noqa: ARG001
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


@v1.get("/playbook", response_model=PlaybookResponse)
async def get_current_playbook(session: AsyncSession | None = Depends(session_dependency), _uid: str | None = Depends(get_current_user_id)):
    if settings.in_memory_mode:
        content = settings.resolve_playbook_path().read_text(encoding="utf-8")
        return PlaybookResponse(
            id="in-memory",
            created_at=datetime.utcnow(),
            content=content,
            change_note="in-memory",
            version_label="in-memory",
        )

    assert session is not None
    result = await session.execute(
        select(PlaybookVersion)
        .where(PlaybookVersion.deleted_at.is_(None))
        .order_by(PlaybookVersion.created_at.desc())
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


@v1.get("/playbook/versions", response_model=list[PlaybookResponse])
async def get_playbook_versions(session: AsyncSession | None = Depends(session_dependency), _uid: str | None = Depends(get_current_user_id)):
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
    assert session is not None
    return await list_playbook_versions(session)


@v1.get("/playbook/versions/{version_id}", response_model=PlaybookResponse)
async def get_playbook_version(version_id: str, session: AsyncSession | None = Depends(session_dependency), _uid: str | None = Depends(get_current_user_id)):
    if settings.in_memory_mode:
        content = settings.resolve_playbook_path().read_text(encoding="utf-8")
        return PlaybookResponse(
            id="in-memory",
            created_at=datetime.utcnow(),
            content=content,
            change_note="in-memory",
            version_label="in-memory",
        )
    assert session is not None
    result = await session.execute(
        select(PlaybookVersion).where(
            PlaybookVersion.id == version_id, PlaybookVersion.deleted_at.is_(None)
        )
    )
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


@v1.put("/playbook", response_model=PlaybookResponse)
async def update_playbook(request: PlaybookUpdateRequest, session: AsyncSession | None = Depends(session_dependency), _uid: str | None = Depends(get_current_user_id)):
    if settings.in_memory_mode:
        return PlaybookResponse(
            id="in-memory",
            created_at=datetime.utcnow(),
            content=request.content,
            change_note=request.change_note,
            version_label="in-memory",
        )
    assert session is not None
    version = PlaybookVersion(content=request.content, change_note=request.change_note, version_label=datetime.utcnow().strftime("%Y-%m-%d"))
    session.add(version)
    await session.flush()
    await write_audit_log(session, "playbook_versions", version.id, "create")
    await persist_chunks(session, version.id, request.content)
    return PlaybookResponse(
        id=version.id,
        created_at=version.created_at,
        content=version.content,
        change_note=version.change_note,
        version_label=version.version_label,
    )


@v1.delete("/gdpr/erase/{analysis_id}", status_code=204)
async def gdpr_erase(analysis_id: str, session: AsyncSession | None = Depends(session_dependency), _uid: str | None = Depends(get_current_user_id)):
    """GDPR right-to-erasure: permanently delete contract text from an analysis."""
    if settings.in_memory_mode:
        IN_MEMORY_RESULTS.pop(analysis_id, None)
        return

    assert session is not None
    result = await session.execute(select(Analysis).where(Analysis.id == analysis_id))
    analysis = result.scalars().first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    analysis.contract_text = "[erased]"
    analysis.result_json = None
    analysis.deleted_at = datetime.utcnow()
    await write_audit_log(session, "analyses", analysis_id, "gdpr_erase")
    await session.flush()


@v1.post("/playbook/reindex")
async def reindex_playbook(body: PlaybookReindexRequest, session: AsyncSession | None = Depends(session_dependency), _uid: str | None = Depends(get_current_user_id)):
    if settings.in_memory_mode:
        return {"status": "ok", "version_id": "in-memory"}
    assert session is not None
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


auth_router = APIRouter(prefix="/v1/auth", tags=["auth"])


@auth_router.post("/register", response_model=UserResponse, status_code=201)
async def register(payload: UserCreate, session: AsyncSession | None = Depends(session_dependency)):
    if settings.in_memory_mode:
        raise HTTPException(status_code=501, detail="Auth not available in test mode")
    assert session is not None
    existing = await session.execute(select(User).where(User.email == payload.email))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(email=payload.email, hashed_password=hash_password(payload.password))
    session.add(user)
    await session.flush()
    logger.info("user_registered", user_id=user.id)
    return UserResponse(id=user.id, email=user.email, created_at=user.created_at)


@auth_router.post("/login", response_model=Token)
async def login(payload: UserLogin, session: AsyncSession | None = Depends(session_dependency)):
    if settings.in_memory_mode:
        raise HTTPException(status_code=501, detail="Auth not available in test mode")
    assert session is not None
    result = await session.execute(
        select(User).where(User.email == payload.email, User.is_active.is_(True))
    )
    user = result.scalars().first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(user.id)
    logger.info("user_login", user_id=user.id)
    return Token(access_token=token)


app.include_router(auth_router)
app.include_router(v1)
