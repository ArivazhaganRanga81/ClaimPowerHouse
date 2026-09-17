from __future__ import annotations

from app.models import (
    AdjudicationJob,
    AgentFinding,
    Claim,
    ClaimStatus,
    JobStatus,
    Recommendation,
    User,
)
from app.schemas import SubmitDecisionRequest
from app.security import Principal
from app.services.audit import verify_audit_chain
from app.services.decisions import submit_decision
from app.services.seed import sid
from app.services.workflow import create_job, execute_job
from sqlalchemy import select


def test_review_requires_human_and_decision_is_audited(session_factory, monkeypatch):
    from app.services import workflow

    monkeypatch.setattr(workflow, "SessionLocal", session_factory)
    with session_factory() as session:
        claim = session.get(Claim, sid("claim-3"))
        user = session.get(User, sid("user-adjudicator"))
        assert claim is not None and user is not None
        job, created = create_job(
            session,
            claim=claim,
            requested_by=user.id,
            idempotency_key="test-auth-job-001",
        )
        assert created
        job_id = job.id

    execute_job(job_id)

    with session_factory() as session:
        job = session.get(AdjudicationJob, job_id)
        claim = session.get(Claim, sid("claim-3"))
        recommendation = session.scalar(
            select(Recommendation).where(Recommendation.job_id == job_id)
        )
        findings = session.scalars(select(AgentFinding).where(AgentFinding.job_id == job_id)).all()
        assert job is not None and claim is not None and recommendation is not None
        assert job.status == JobStatus.WAITING_FOR_HUMAN
        assert claim.status == ClaimStatus.NEW
        assert recommendation.requires_human_review is True
        assert recommendation.recommended_action == "PEND_REQUEST_DOCUMENTATION"
        assert any("AUTH_001" in finding.reason_codes for finding in findings)

        principal = Principal(
            user_id=sid("user-adjudicator"), role="ADJUDICATOR", display_name="Demo"
        )
        decision = submit_decision(
            session,
            claim=claim,
            principal=principal,
            request=SubmitDecisionRequest(
                job_id=job_id,
                recommendation_id=recommendation.id,
                recommendation_response="ACCEPTED",
                disposition="PENDED",
                expected_claim_version=claim.version,
                idempotency_key="decision-auth-001",
                attested=True,
            ),
        )
        assert decision.disposition == "PENDED"
        assert claim.status == ClaimStatus.PENDED
        assert job.status == JobStatus.COMPLETED
        valid, count = verify_audit_chain(session)
        assert valid and count == 1


def test_job_idempotency(session):
    claim = session.get(Claim, sid("claim-1"))
    assert claim is not None
    user_id = sid("user-adjudicator")
    first, first_created = create_job(
        session, claim=claim, requested_by=user_id, idempotency_key="same-request-001"
    )
    second, second_created = create_job(
        session, claim=claim, requested_by=user_id, idempotency_key="same-request-001"
    )
    assert first_created is True
    assert second_created is False
    assert first.id == second.id
