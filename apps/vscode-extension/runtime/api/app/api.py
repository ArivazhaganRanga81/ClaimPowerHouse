from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .database import SessionLocal, get_session
from .models import (
    AdjudicationJob,
    AgentFinding,
    AuthSession,
    AuditEvent,
    BackupRecord,
    Claim,
    ClaimDiagnosis,
    ClaimLine,
    ClaimStatus,
    ImportBatch,
    JobEvent,
    JobStatus,
    Member,
    PolicyDocument,
    PolicyVersion,
    Provider,
    PublicationState,
    Recommendation,
    User,
)
from .schemas import (
    AuditEventView,
    ClaimDetail,
    ClaimPage,
    ClaimSummary,
    CreatePolicyRequest,
    CreatePolicyVersionRequest,
    DecisionView,
    FindingView,
    JobView,
    ImportClaimsRequest,
    LoginRequest,
    PolicyEvidence,
    PolicySearchRequest,
    PolicyVersionView,
    PolicyView,
    RecommendationView,
    StartAdjudicationRequest,
    SubmitDecisionRequest,
    UpdatePolicyVersionRequest,
    UserView,
)
from .security import (
    SESSION_COOKIE,
    Principal,
    create_login_session,
    get_principal,
    token_hash,
    verify_password,
    ensure_role,
)
from .services.audit import append_audit_event
from .services.backup import create_backup, validate_backup
from .services.decisions import submit_decision
from .services.rag import rebuild_lexical_index, replace_policy_chunks, search_policies
from .services.workflow import create_job, execute_job

router = APIRouter(prefix="/api/v1")


def _claim_query():
    return select(Claim).options(
        selectinload(Claim.member),
        selectinload(Claim.provider),
        selectinload(Claim.lines),
        selectinload(Claim.diagnoses),
    )


@router.post("/auth/login", response_model=UserView)
def login(request: LoginRequest, response: Response, session: Session = Depends(get_session)) -> UserView:
    user = session.scalar(select(User).where(User.email == request.email, User.active.is_(True)))
    if user is None or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    auth_session, raw_token = create_login_session(user)
    session.add(auth_session)
    session.commit()
    response.set_cookie(
        SESSION_COOKIE,
        raw_token,
        httponly=True,
        samesite="strict",
        secure=False,
        max_age=8 * 60 * 60,
        path="/",
    )
    return UserView(id=user.id, email=user.email, display_name=user.display_name, role=user.role)


@router.post("/auth/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> None:
    raw_token = request.cookies.get(SESSION_COOKIE)
    if raw_token:
        auth_session = session.scalar(
            select(AuthSession).where(AuthSession.token_hash == token_hash(raw_token))
        )
        if auth_session:
            auth_session.revoked_at = datetime.now(UTC)
            session.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me")
def me(principal: Principal = Depends(get_principal)) -> dict[str, str]:
    return {
        "id": principal.user_id,
        "role": principal.role,
        "display_name": principal.display_name,
    }


@router.get("/claims", response_model=ClaimPage)
def list_claims(
    claim_status: ClaimStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
) -> ClaimPage:
    filters = [Claim.status == claim_status] if claim_status else []
    total = session.scalar(select(func.count()).select_from(Claim).where(*filters)) or 0
    claims = session.scalars(
        select(Claim)
        .where(*filters)
        .order_by(Claim.risk_score.desc(), Claim.received_at)
        .limit(limit)
        .offset(offset)
    ).all()
    return ClaimPage(
        items=[ClaimSummary.model_validate(claim) for claim in claims],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/claims/{claim_id}", response_model=ClaimDetail)
def get_claim(
    claim_id: str,
    _: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
) -> ClaimDetail:
    claim = session.scalar(_claim_query().where(Claim.id == claim_id))
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    return ClaimDetail.model_validate(claim)


@router.post("/claims/{claim_id}/adjudications", response_model=JobView, status_code=202)
def start_adjudication(
    claim_id: str,
    request: StartAdjudicationRequest,
    background_tasks: BackgroundTasks,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
) -> JobView:
    claim = session.scalar(_claim_query().where(Claim.id == claim_id))
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    if claim.status in {ClaimStatus.APPROVED, ClaimStatus.DENIED, ClaimStatus.CANCELLED}:
        raise HTTPException(status_code=409, detail="Terminal claim cannot be reviewed")
    job, created = create_job(
        session,
        claim=claim,
        requested_by=principal.user_id,
        idempotency_key=request.idempotency_key,
    )
    if created:
        background_tasks.add_task(execute_job, job.id)
    return JobView.model_validate(job)


@router.get("/adjudications/{job_id}", response_model=JobView)
def get_job(
    job_id: str,
    _: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
) -> JobView:
    job = session.get(AdjudicationJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobView.model_validate(job)


@router.get("/adjudications/{job_id}/findings", response_model=list[FindingView])
def get_findings(
    job_id: str,
    _: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
) -> list[FindingView]:
    findings = session.scalars(
        select(AgentFinding).where(AgentFinding.job_id == job_id).order_by(AgentFinding.created_at)
    ).all()
    return [FindingView.model_validate(item) for item in findings]


@router.get("/adjudications/{job_id}/recommendation", response_model=RecommendationView)
def get_recommendation(
    job_id: str,
    _: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
) -> RecommendationView:
    recommendation = session.scalar(select(Recommendation).where(Recommendation.job_id == job_id))
    if recommendation is None:
        raise HTTPException(status_code=404, detail="Recommendation not ready")
    return RecommendationView.model_validate(recommendation)


async def _event_stream(job_id: str, after: int) -> AsyncIterator[str]:
    cursor = after
    idle_rounds = 0
    while idle_rounds < 150:
        with SessionLocal() as session:
            job = session.get(AdjudicationJob, job_id)
            if job is None:
                yield 'event: error\ndata: {"message":"Job not found"}\n\n'
                return
            events = session.scalars(
                select(JobEvent)
                .where(JobEvent.job_id == job_id, JobEvent.sequence > cursor)
                .order_by(JobEvent.sequence)
            ).all()
            for event in events:
                cursor = event.sequence
                body = json.dumps(
                    {
                        "type": event.event_type,
                        "payload": event.payload,
                        "created_at": event.created_at.isoformat(),
                    }
                )
                yield f"id: {event.sequence}\nevent: {event.event_type}\ndata: {body}\n\n"
            idle_rounds = 0 if events else idle_rounds + 1
            if (
                job.status
                in {
                    JobStatus.COMPLETED,
                    JobStatus.FAILED,
                    JobStatus.CANCELLED,
                    JobStatus.WAITING_FOR_HUMAN,
                }
                and not events
            ):
                return
        await asyncio.sleep(0.2)


@router.get("/adjudications/{job_id}/events")
def stream_events(
    job_id: str,
    last_event_id: int | None = Header(default=None, alias="Last-Event-ID"),
    _: Principal = Depends(get_principal),
) -> StreamingResponse:
    return StreamingResponse(
        _event_stream(job_id, last_event_id or 0),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/claims/{claim_id}/decisions", response_model=DecisionView)
def decide_claim(
    claim_id: str,
    request: SubmitDecisionRequest,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
) -> DecisionView:
    claim = session.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    decision = submit_decision(session, claim=claim, request=request, principal=principal)
    return DecisionView.model_validate(decision)


@router.get("/claims/{claim_id}/audit", response_model=list[AuditEventView])
def claim_audit(
    claim_id: str,
    _: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
) -> list[AuditEventView]:
    events = session.scalars(
        select(AuditEvent).where(AuditEvent.claim_id == claim_id).order_by(AuditEvent.sequence)
    ).all()
    return [AuditEventView.model_validate(event) for event in events]


@router.post("/rag/query-test", response_model=list[PolicyEvidence])
def query_rag(
    request: PolicySearchRequest,
    _: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
) -> list[PolicyEvidence]:
    return search_policies(
        session,
        query=request.query,
        payer_code=request.payer_code,
        plan_code=request.plan_code,
        service_date=request.service_date,
        limit=request.limit,
    )


@router.post("/rag/indexes/rebuild")
def build_index(
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    if principal.role not in {"ADMINISTRATOR", "SUPERVISOR"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Administrator role required"
        )
    return rebuild_lexical_index(session)


@router.get("/policies", response_model=list[PolicyView])
def list_policies(
    _: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
) -> list[PolicyView]:
    policies = session.scalars(select(PolicyDocument).order_by(PolicyDocument.policy_code)).all()
    return [PolicyView.model_validate(item) for item in policies]


@router.post("/policies", response_model=PolicyView, status_code=201)
def create_policy(
    request: CreatePolicyRequest,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
) -> PolicyView:
    ensure_role(principal, "ADMINISTRATOR", "SUPERVISOR")
    if session.scalar(select(PolicyDocument).where(PolicyDocument.policy_code == request.policy_code)):
        raise HTTPException(status_code=409, detail="Policy code already exists")
    policy = PolicyDocument(**request.model_dump())
    session.add(policy)
    session.flush()
    append_audit_event(
        session,
        actor_id=principal.user_id,
        actor_type="USER",
        claim_id=None,
        correlation_id=policy.id,
        event_type="POLICY_CREATED",
        before=None,
        after=request.model_dump(mode="json"),
    )
    session.commit()
    return PolicyView.model_validate(policy)


@router.get("/policies/{policy_id}/versions", response_model=list[PolicyVersionView])
def list_policy_versions(
    policy_id: str,
    _: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
) -> list[PolicyVersionView]:
    versions = session.scalars(
        select(PolicyVersion)
        .where(PolicyVersion.policy_id == policy_id)
        .order_by(PolicyVersion.effective_from.desc())
    ).all()
    return [PolicyVersionView.model_validate(item) for item in versions]


@router.post("/policies/{policy_id}/versions", response_model=PolicyVersionView, status_code=201)
def create_policy_version(
    policy_id: str,
    request: CreatePolicyVersionRequest,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
) -> PolicyVersionView:
    ensure_role(principal, "ADMINISTRATOR", "SUPERVISOR")
    if session.get(PolicyDocument, policy_id) is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    if request.effective_to and request.effective_to < request.effective_from:
        raise HTTPException(status_code=422, detail="Effective end precedes effective start")
    duplicate = session.scalar(
        select(PolicyVersion).where(
            PolicyVersion.policy_id == policy_id,
            PolicyVersion.version == request.version,
        )
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="Policy version already exists")
    version = PolicyVersion(
        policy_id=policy_id,
        **request.model_dump(),
        state=PublicationState.DRAFT,
        content_hash=hashlib.sha256(request.content.encode()).hexdigest(),
    )
    session.add(version)
    session.flush()
    replace_policy_chunks(session, version)
    append_audit_event(
        session,
        actor_id=principal.user_id,
        actor_type="USER",
        claim_id=None,
        correlation_id=version.id,
        event_type="POLICY_VERSION_CREATED",
        before=None,
        after={"policy_id": policy_id, "version": request.version, "state": "DRAFT"},
    )
    session.commit()
    return PolicyVersionView.model_validate(version)


@router.put("/policy-versions/{version_id}", response_model=PolicyVersionView)
def update_policy_version(
    version_id: str,
    request: UpdatePolicyVersionRequest,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
) -> PolicyVersionView:
    ensure_role(principal, "ADMINISTRATOR", "SUPERVISOR")
    version = session.get(PolicyVersion, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Policy version not found")
    if version.state != PublicationState.DRAFT:
        raise HTTPException(status_code=409, detail="Only draft policy versions are editable")
    before_hash = version.content_hash
    version.content = request.content
    version.effective_from = request.effective_from
    version.effective_to = request.effective_to
    version.content_hash = hashlib.sha256(request.content.encode()).hexdigest()
    replace_policy_chunks(session, version)
    append_audit_event(
        session,
        actor_id=principal.user_id,
        actor_type="USER",
        claim_id=None,
        correlation_id=version.id,
        event_type="POLICY_VERSION_UPDATED",
        before={"content_hash": before_hash},
        after={"content_hash": version.content_hash},
    )
    session.commit()
    return PolicyVersionView.model_validate(version)


@router.post("/policy-versions/{version_id}/publish", response_model=PolicyVersionView)
def publish_policy_version(
    version_id: str,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
) -> PolicyVersionView:
    ensure_role(principal, "ADMINISTRATOR", "SUPERVISOR")
    version = session.get(PolicyVersion, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Policy version not found")
    before = version.state.value
    version.state = PublicationState.ACTIVE
    if not version.chunks:
        replace_policy_chunks(session, version)
    append_audit_event(
        session,
        actor_id=principal.user_id,
        actor_type="USER",
        claim_id=None,
        correlation_id=version.id,
        event_type="POLICY_VERSION_PUBLISHED",
        before={"state": before},
        after={"state": version.state.value, "content_hash": version.content_hash},
    )
    session.commit()
    return PolicyVersionView.model_validate(version)


@router.post("/claims/import", status_code=201)
def import_claims(
    request: ImportClaimsRequest,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    ensure_role(principal, "ADMINISTRATOR", "SUPERVISOR")
    source_hash = hashlib.sha256(
        request.model_dump_json(exclude_none=False).encode()
    ).hexdigest()
    batch = ImportBatch(
        source_type=request.source_type,
        source_hash=source_hash,
        status="RUNNING",
        record_count=len(request.claims),
        requested_by=principal.user_id,
        manifest={"schema": "cph-json-1"},
    )
    session.add(batch)
    session.flush()
    imported = 0
    errors: list[dict[str, str]] = []
    for source in request.claims:
        if session.scalar(select(Claim).where(Claim.external_claim_id == source.external_claim_id)):
            errors.append({"claim": source.external_claim_id, "error": "duplicate external ID"})
            continue
        member = session.scalar(
            select(Member).where(Member.external_id == source.member_external_id)
        )
        provider = session.scalar(
            select(Provider).where(Provider.external_id == source.provider_external_id)
        )
        if member is None or provider is None:
            errors.append({"claim": source.external_claim_id, "error": "member/provider not found"})
            continue
        claim = Claim(
            external_claim_id=source.external_claim_id,
            member_id=member.id,
            provider_id=provider.id,
            payer_code=source.payer_code,
            plan_code=source.plan_code,
            claim_type="PROFESSIONAL",
            status=ClaimStatus.NEW,
            billed_amount_minor=sum(line.billed_amount_minor for line in source.lines),
            service_start=source.service_start,
            service_end=source.service_end,
        )
        session.add(claim)
        session.flush()
        for number, line in enumerate(source.lines, 1):
            session.add(ClaimLine(claim_id=claim.id, line_number=number, **line.model_dump()))
        for number, code in enumerate(source.diagnoses, 1):
            session.add(ClaimDiagnosis(claim_id=claim.id, code=code, sequence=number))
        imported += 1
    batch.imported_count = imported
    batch.error_count = len(errors)
    batch.status = "COMPLETED_WITH_ERRORS" if errors else "COMPLETED"
    batch.manifest = {"schema": "cph-json-1", "errors": errors[:100]}
    append_audit_event(
        session,
        actor_id=principal.user_id,
        actor_type="USER",
        claim_id=None,
        correlation_id=batch.id,
        event_type="CLAIMS_IMPORTED",
        before=None,
        after={"imported": imported, "errors": len(errors), "source_hash": source_hash},
    )
    session.commit()
    return {"batch_id": batch.id, "imported": imported, "errors": errors}


@router.get("/admin/backups")
def list_backups(
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
) -> list[dict[str, object]]:
    ensure_role(principal, "ADMINISTRATOR")
    records = session.scalars(select(BackupRecord).order_by(BackupRecord.created_at.desc())).all()
    return [
        {
            "id": item.id,
            "artifact_name": item.artifact_name,
            "artifact_hash": item.artifact_hash,
            "size_bytes": item.size_bytes,
            "status": item.status,
            "created_at": item.created_at,
        }
        for item in records
    ]


@router.post("/admin/backups", status_code=201)
def backup_now(
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    ensure_role(principal, "ADMINISTRATOR")
    record = create_backup(session, principal.user_id)
    return {
        "id": record.id,
        "artifact_name": record.artifact_name,
        "artifact_hash": record.artifact_hash,
        "size_bytes": record.size_bytes,
        "status": record.status,
    }


@router.post("/admin/backups/{artifact_name}/validate")
def validate_backup_artifact(
    artifact_name: str,
    principal: Principal = Depends(get_principal),
) -> dict[str, object]:
    ensure_role(principal, "ADMINISTRATOR")
    try:
        return validate_backup(artifact_name)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
