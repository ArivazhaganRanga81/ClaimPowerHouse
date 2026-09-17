import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (                                                          
    AdjudicationJob,
    Claim,                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              
    ClaimDecision,
    ClaimStatus,
    JobStatus,
    Recommendation,
    RecommendationStatus,
)
from ..schemas import SubmitDecisionRequest
from ..security import Principal
from .audit import append_audit_event
from .workflow import emit

DISPOSITION_STATUS = {
    "APPROVED": ClaimStatus.APPROVED,
    "DENIED": ClaimStatus.DENIED,
    "PENDED": ClaimStatus.PENDED,
    "NEEDS_REVIEW": ClaimStatus.NEEDS_REVIEW,
}


def submit_decision(
    session: Session,
    *,
    claim: Claim,
    request: SubmitDecisionRequest,
    principal: Principal,
) -> ClaimDecision:
    existing = session.scalar(
        select(ClaimDecision).where(
            ClaimDecision.actor_user_id == principal.user_id,
            ClaimDecision.idempotency_key == request.idempotency_key,
        )
    )
    if existing:
        return existing
    if not request.attested:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Attestation is required"
        )
    if claim.version != request.expected_claim_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Claim changed; reload before deciding",
                "current_version": claim.version,
            },
        )

    recommendation = None
    if request.recommendation_id:
        recommendation = session.get(Recommendation, request.recommendation_id)
        if recommendation is None or recommendation.claim_id != claim.id:
            raise HTTPException(status_code=404, detail="Recommendation not found for claim")
        if request.recommendation_response is None:
            raise HTTPException(status_code=422, detail="Recommendation response is required")
        if request.recommendation_response != "ACCEPTED" and not request.override_reason:
            raise HTTPException(status_code=422, detail="Override reason is required")
        recommendation.status = RecommendationStatus(request.recommendation_response)

    if request.disposition in {"APPROVED", "DENIED"} and request.job_id is None:
        raise HTTPException(status_code=422, detail="A completed review job is required")

    job = session.get(AdjudicationJob, request.job_id) if request.job_id else None
    if job is not None:
        if job.claim_id != claim.id or job.status != JobStatus.WAITING_FOR_HUMAN:
            raise HTTPException(
                status_code=409, detail="Job is not awaiting a decision for this claim"
            )

    before = {"status": claim.status.value, "version": claim.version}
    claim.status = DISPOSITION_STATUS[request.disposition]
    claim.version += 1
    after = {"status": claim.status.value, "version": claim.version}
    decision = ClaimDecision(
        claim_id=claim.id,
        job_id=job.id if job else None,
        recommendation_id=recommendation.id if recommendation else None,
        disposition=request.disposition,
        actor_user_id=principal.user_id,
        idempotency_key=request.idempotency_key,
        expected_claim_version=request.expected_claim_version,
        override_reason=request.override_reason,
        note=request.note,
        attested=request.attested,
    )
    session.add(decision)
    session.flush()
    correlation_id = job.correlation_id if job else uuid.uuid4().hex
    append_audit_event(
        session,
        actor_id=principal.user_id,
        actor_type="USER",
        claim_id=claim.id,
        correlation_id=correlation_id,
        event_type="CLAIM_DECISION_SUBMITTED",
        before=before,
        after=after,
        details={
            "decision_id": decision.id,
            "recommendation_id": recommendation.id if recommendation else None,
            "recommendation_response": request.recommendation_response,
            "override_reason": request.override_reason,
        },
    )
    if job:
        job.status = JobStatus.COMPLETED
        emit(session, job.id, "DECISION_COMMITTED", {"decision_id": decision.id, **after})
    session.commit()
    session.refresh(decision)
    return decision
