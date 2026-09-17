from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..database import SessionLocal
from ..models import (
    AdjudicationJob,
    AgentFinding,
    AgentRun,
    Claim,
    JobEvent,
    JobStatus,
    LlmCall,
    Recommendation,
    RecommendationStatus,
    StepStatus,
)
from .llm import SynthesisInput, get_llm_gateway
from .rag import search_policies
from .rules import run_rules

ALLOWED_ACTIONS = [
    "APPROVE_REVIEW",
    "DENY_REVIEW",
    "PEND_REQUEST_DOCUMENTATION",
    "ROUTE_SPECIALIST",
    "CORRECT_AND_REVIEW",
    "INSUFFICIENT_EVIDENCE",
]


def claim_snapshot(claim: Claim) -> dict[str, Any]:
    return {
        "id": claim.id,
        "external_claim_id": claim.external_claim_id,
        "version": claim.version,
        "payer_code": claim.payer_code,
        "plan_code": claim.plan_code,
        "claim_type": claim.claim_type,
        "service_start": claim.service_start.isoformat(),
        "service_end": claim.service_end.isoformat(),
        "billed_amount_minor": claim.billed_amount_minor,
        "currency": claim.currency,
        "member_id": claim.member_id,
        "provider_id": claim.provider_id,
        "diagnoses": [item.code for item in claim.diagnoses],
        "lines": [
            {
                "line_number": line.line_number,
                "procedure_code": line.procedure_code,
                "modifiers": line.modifiers,
                "units": line.units,
                "billed_amount_minor": line.billed_amount_minor,
                "authorization_number": line.authorization_number,
            }
            for line in claim.lines
        ],
    }


def _hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def emit(session: Session, job_id: str, event_type: str, payload: dict[str, Any]) -> JobEvent:
    current = session.scalar(select(func.max(JobEvent.sequence)).where(JobEvent.job_id == job_id))
    event = JobEvent(
        job_id=job_id,
        sequence=(current or 0) + 1,
        event_type=event_type,
        payload=payload,
    )
    session.add(event)
    session.flush()
    return event


def create_job(
    session: Session,
    *,
    claim: Claim,
    requested_by: str,
    idempotency_key: str,
) -> tuple[AdjudicationJob, bool]:
    existing = session.scalar(
        select(AdjudicationJob).where(
            AdjudicationJob.requested_by == requested_by,
            AdjudicationJob.idempotency_key == idempotency_key,
        )
    )
    if existing:
        return existing, False
    snapshot = claim_snapshot(claim)
    job = AdjudicationJob(
        claim_id=claim.id,
        claim_version=claim.version,
        idempotency_key=idempotency_key,
        correlation_id=uuid.uuid4().hex,
        requested_by=requested_by,
        claim_snapshot=snapshot,
        snapshot_hash=_hash(snapshot),
    )
    session.add(job)
    session.flush()
    emit(session, job.id, "JOB_QUEUED", {"claim_id": claim.id, "claim_version": claim.version})
    session.commit()
    return job, True


def _start_agent(session: Session, job_id: str, agent_type: str) -> AgentRun:
    run = AgentRun(job_id=job_id, agent_type=agent_type, status=StepStatus.RUNNING)
    session.add(run)
    session.flush()
    emit(session, job_id, "AGENT_STARTED", {"agent_type": agent_type, "agent_run_id": run.id})
    return run


def _finish_agent(session: Session, run: AgentRun, findings: list[AgentFinding]) -> None:
    run.status = StepStatus.SUCCEEDED
    run.output_hash = _hash([finding.id for finding in findings])
    emit(
        session,
        run.job_id,
        "AGENT_COMPLETED",
        {"agent_type": run.agent_type, "agent_run_id": run.id, "finding_count": len(findings)},
    )


def _finding(
    session: Session,
    *,
    job_id: str,
    run: AgentRun,
    finding_type: str,
    severity: str,
    conclusion: str,
    reason_codes: list[str],
    evidence: list[dict[str, Any]],
    action: str | None,
    confidence_milli: int = 1000,
    limitations: list[str] | None = None,
) -> AgentFinding:
    finding = AgentFinding(
        job_id=job_id,
        agent_run_id=run.id,
        finding_type=finding_type,
        severity=severity,
        conclusion=conclusion,
        confidence_milli=confidence_milli,
        reason_codes=reason_codes,
        evidence=evidence,
        recommended_action=action,
        limitations=limitations or [],
    )
    session.add(finding)
    session.flush()
    return finding


def execute_job(job_id: str) -> None:
    with SessionLocal() as session:
        job = session.get(AdjudicationJob, job_id)
        if job is None or job.status not in {JobStatus.QUEUED, JobStatus.FAILED}:
            return
        try:
            claim = session.scalar(
                select(Claim)
                .options(selectinload(Claim.lines), selectinload(Claim.diagnoses))
                .where(Claim.id == job.claim_id)
            )
            if claim is None:
                raise ValueError("Claim no longer exists")
            if claim.version != job.claim_version:
                raise ValueError("Claim changed after the job snapshot was created")
            job.status = JobStatus.RUNNING
            emit(session, job.id, "JOB_STARTED", {})

            validation_run = _start_agent(session, job.id, "INTAKE_VALIDATION")
            validation_findings: list[AgentFinding] = []
            if not claim.lines or not claim.diagnoses:
                validation_findings.append(
                    _finding(
                        session,
                        job_id=job.id,
                        run=validation_run,
                        finding_type="CLAIM_INCOMPLETE",
                        severity="HIGH",
                        conclusion="Claim is missing lines or diagnoses.",
                        reason_codes=["REQ_FIELD_001"],
                        evidence=[],
                        action="CORRECT_AND_REVIEW",
                    )
                )
            _finish_agent(session, validation_run, validation_findings)

            rules_run = _start_agent(session, job.id, "RULES")
            rule_results = run_rules(session, claim, job.id)
            rule_findings: list[AgentFinding] = []
            for result in rule_results:
                if result.passed:
                    continue
                code = str(result.evidence.get("rule_code", "RULE_FAILURE"))
                action = (
                    "PEND_REQUEST_DOCUMENTATION" if code == "AUTH_001" else "CORRECT_AND_REVIEW"
                )
                rule_findings.append(
                    _finding(
                        session,
                        job_id=job.id,
                        run=rules_run,
                        finding_type=code,
                        severity=result.severity,
                        conclusion=result.message,
                        reason_codes=[code],
                        evidence=[
                            {"type": "RULE_RESULT", "rule_result_id": result.id, **result.evidence}
                        ],
                        action=action,
                    )
                )
            _finish_agent(session, rules_run, rule_findings)

            coding_run = _start_agent(session, job.id, "CODING_RISK")
            coding_findings: list[AgentFinding] = []
            if claim.risk_score >= 80:
                coding_findings.append(
                    _finding(
                        session,
                        job_id=job.id,
                        run=coding_run,
                        finding_type="HIGH_RISK_REVIEW",
                        severity="HIGH",
                        conclusion="Configured risk threshold requires specialist review.",
                        reason_codes=["HIGH_RISK"],
                        evidence=[{"type": "CLAIM_ATTRIBUTE", "risk_score": claim.risk_score}],
                        action="ROUTE_SPECIALIST",
                        confidence_milli=1000,
                    )
                )
            _finish_agent(session, coding_run, coding_findings)

            policy_run = _start_agent(session, job.id, "POLICY_EVIDENCE")
            query_parts = [line.procedure_code for line in claim.lines]
            query_parts.extend(finding.conclusion for finding in rule_findings)
            policy_evidence = search_policies(
                session,
                query=" ".join(query_parts),
                payer_code=claim.payer_code,
                plan_code=claim.plan_code,
                service_date=claim.service_start,
                limit=5,
            )
            policy_findings: list[AgentFinding] = []
            if rule_findings and not policy_evidence:
                policy_findings.append(
                    _finding(
                        session,
                        job_id=job.id,
                        run=policy_run,
                        finding_type="POLICY_EVIDENCE_MISSING",
                        severity="HIGH",
                        conclusion="No applicable approved policy evidence was retrieved.",
                        reason_codes=["INSUFFICIENT_EVIDENCE"],
                        evidence=[],
                        action="INSUFFICIENT_EVIDENCE",
                        limitations=["No policy citation available"],
                    )
                )
            _finish_agent(session, policy_run, policy_findings)

            all_findings = validation_findings + rule_findings + coding_findings + policy_findings
            evidence = [item.model_dump(mode="json") for item in policy_evidence]
            synthesis_run = _start_agent(session, job.id, "RECOMMENDATION_SYNTHESIS")
            gateway = get_llm_gateway()
            output = gateway.synthesize(
                SynthesisInput(
                    job_id=job.id,
                    claim_snapshot=job.claim_snapshot,
                    findings=[
                        {
                            "id": finding.id,
                            "severity": finding.severity,
                            "reason_codes": finding.reason_codes,
                            "recommended_action": finding.recommended_action,
                        }
                        for finding in all_findings
                    ],
                    evidence=evidence,
                    allowed_actions=ALLOWED_ACTIONS,
                )
            )
            recommendation = Recommendation(
                job_id=job.id,
                claim_id=claim.id,
                status=RecommendationStatus.READY,
                recommended_action=output.recommended_action,
                summary=output.summary,
                reason_codes=output.reason_codes,
                finding_ids=output.finding_ids,
                evidence=output.evidence,
                suggested_edits=output.suggested_edits,
                missing_evidence=output.missing_evidence,
                adjudicator_note=output.adjudicator_note,
                requires_human_review=True,
            )
            session.add(recommendation)
            session.add(
                LlmCall(
                    job_id=job.id,
                    provider=output.provider,
                    model=output.model,
                    prompt_version="synthesis-1.0",
                    request_hash=output.request_hash,
                    response_hash=output.response_hash,
                    input_tokens=output.input_tokens,
                    output_tokens=output.output_tokens,
                    latency_ms=output.latency_ms,
                    status="DEGRADED" if output.error_message else "SUCCEEDED",
                    error_message=output.error_message,
                )
            )
            session.flush()
            _finish_agent(session, synthesis_run, [])
            job.status = JobStatus.WAITING_FOR_HUMAN
            emit(
                session,
                job.id,
                "HUMAN_REVIEW_REQUIRED",
                {
                    "recommendation_id": recommendation.id,
                    "action": recommendation.recommended_action,
                },
            )
            session.commit()
        except Exception as exc:
            session.rollback()
            job = session.get(AdjudicationJob, job_id)
            if job is not None:
                job.status = JobStatus.FAILED
                job.error_message = str(exc)[:2000]
                emit(session, job.id, "JOB_FAILED", {"message": "Review processing failed safely."})
                session.commit()
