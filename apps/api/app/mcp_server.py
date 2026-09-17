from __future__ import annotations

import json
from datetime import date
from typing import Any

from mcp.server.fastmcp import FastMCP
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .database import SessionLocal
from .models import AdjudicationJob, AgentFinding, Claim, Recommendation
from .services.rag import search_policies
from .services.rules import REGISTRY, active_rule_versions
from .services.workflow import ALLOWED_ACTIONS, claim_snapshot

mcp = FastMCP(
    "Claim Power House",
    instructions=(
        "Synthetic claim-review resources and read-only/proposal tools. "
        "No tool exposed by this server can approve, deny, or mutate a claim."
    ),
    streamable_http_path="/",
    stateless_http=True,
    json_response=True,
)


def _load_claim(claim_id: str) -> Claim:
    with SessionLocal() as session:
        claim = session.scalar(
            select(Claim)
            .options(selectinload(Claim.lines), selectinload(Claim.diagnoses))
            .where(Claim.id == claim_id)
        )
        if claim is None:
            raise ValueError("Claim not found")
        session.expunge(claim)
        return claim


@mcp.tool()
def get_claim_snapshot(claim_id: str) -> dict[str, Any]:
    """Return a canonical, synthetic claim snapshot for read-only analysis."""
    return claim_snapshot(_load_claim(claim_id))


@mcp.tool()
def preview_rule_set(claim_id: str) -> list[dict[str, Any]]:
    """Evaluate active deterministic rules without storing results or changing the claim."""
    with SessionLocal() as session:
        claim = session.scalar(
            select(Claim)
            .options(selectinload(Claim.lines), selectinload(Claim.diagnoses))
            .where(Claim.id == claim_id)
        )
        if claim is None:
            raise ValueError("Claim not found")
        results: list[dict[str, Any]] = []
        for rule, version in active_rule_versions(session, claim.service_start):
            implementation = REGISTRY.get(rule.implementation_key)
            if implementation is None:
                continue
            result = implementation(session, claim, version.parameters)
            results.append(
                {
                    "rule_code": rule.code,
                    "rule_version": version.version,
                    "passed": result.passed,
                    "severity": rule.severity,
                    "message": result.message,
                    "evidence": result.evidence,
                }
            )
        return results


@mcp.tool()
def search_policy_chunks(
    query: str,
    payer_code: str,
    plan_code: str,
    service_date: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Retrieve approved, effective-dated policy evidence for the supplied scope."""
    parsed_date = date.fromisoformat(service_date)
    with SessionLocal() as session:
        return [
            item.model_dump(mode="json")
            for item in search_policies(
                session,
                query=query,
                payer_code=payer_code,
                plan_code=plan_code,
                service_date=parsed_date,
                limit=min(max(limit, 1), 20),
            )
        ]


@mcp.tool()
def get_run_status(run_id: str) -> dict[str, Any]:
    """Return the current status of an adjudication job."""
    with SessionLocal() as session:
        job = session.get(AdjudicationJob, run_id)
        if job is None:
            raise ValueError("Run not found")
        return {
            "run_id": job.id,
            "claim_id": job.claim_id,
            "claim_version": job.claim_version,
            "status": job.status.value,
            "error_message": job.error_message,
        }


@mcp.tool()
def get_agent_findings(run_id: str) -> list[dict[str, Any]]:
    """Return persisted, structured specialist findings for a run."""
    with SessionLocal() as session:
        findings = session.scalars(
            select(AgentFinding)
            .where(AgentFinding.job_id == run_id)
            .order_by(AgentFinding.created_at)
        ).all()
        return [
            {
                "finding_id": item.id,
                "finding_type": item.finding_type,
                "severity": item.severity,
                "conclusion": item.conclusion,
                "reason_codes": item.reason_codes,
                "evidence": item.evidence,
                "recommended_action": item.recommended_action,
                "limitations": item.limitations,
            }
            for item in findings
        ]


@mcp.tool()
def propose_recommendation(
    recommended_action: str,
    summary: str,
    reason_codes: list[str],
    evidence_ids: list[str],
) -> dict[str, Any]:
    """Validate and return a non-persistent recommendation proposal for human review."""
    if recommended_action not in ALLOWED_ACTIONS:
        raise ValueError(f"Action is not allowed: {recommended_action}")
    return {
        "recommended_action": recommended_action,
        "summary": summary[:2000],
        "reason_codes": reason_codes[:20],
        "evidence_ids": evidence_ids[:50],
        "requires_human_review": True,
        "persisted": False,
    }


@mcp.resource("claim://claims/{claim_id}")
def claim_resource(claim_id: str) -> str:
    """Canonical synthetic claim resource."""
    return json.dumps(get_claim_snapshot(claim_id), sort_keys=True, default=str)


@mcp.resource("claim://runs/{run_id}/findings")
def findings_resource(run_id: str) -> str:
    """Structured findings resource for an adjudication run."""
    return json.dumps(get_agent_findings(run_id), sort_keys=True, default=str)


@mcp.resource("claim://runs/{run_id}/recommendation")
def recommendation_resource(run_id: str) -> str:
    """Human-gated recommendation for an adjudication run."""
    with SessionLocal() as session:
        item = session.scalar(select(Recommendation).where(Recommendation.job_id == run_id))
        if item is None:
            raise ValueError("Recommendation not found")
        return json.dumps(
            {
                "recommendation_id": item.id,
                "status": item.status.value,
                "recommended_action": item.recommended_action,
                "summary": item.summary,
                "reason_codes": item.reason_codes,
                "evidence": item.evidence,
                "requires_human_review": item.requires_human_review,
            },
            sort_keys=True,
            default=str,
        )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
