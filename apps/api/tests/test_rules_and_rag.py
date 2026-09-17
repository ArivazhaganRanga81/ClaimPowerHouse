from __future__ import annotations

from datetime import date

from app.models import Claim
from app.services.rag import search_policies
from app.services.rules import run_rules
from app.services.seed import sid
from app.services.workflow import create_job


def test_excess_units_fails_deterministic_rule(session):
    claim = session.get(Claim, sid("claim-2"))
    assert claim is not None
    job, _ = create_job(
        session,
        claim=claim,
        requested_by=sid("user-adjudicator"),
        idempotency_key="rules-unit-job",
    )
    results = run_rules(session, claim, job.id)
    by_code = {result.evidence["rule_code"]: result for result in results}
    assert by_code["UNIT_LIMIT_001"].passed is False
    assert by_code["UNIT_LIMIT_001"].evidence["violations"][0]["maximum_units"] == 5


def test_missing_authorization_fails_deterministic_rule(session):
    claim = session.get(Claim, sid("claim-3"))
    assert claim is not None
    job, _ = create_job(
        session,
        claim=claim,
        requested_by=sid("user-adjudicator"),
        idempotency_key="rules-auth-job",
    )
    results = run_rules(session, claim, job.id)
    by_code = {result.evidence["rule_code"]: result for result in results}
    assert by_code["AUTH_001"].passed is False


def test_policy_search_filters_and_cites(session):
    results = search_policies(
        session,
        query="27447 prior authorization missing",
        payer_code="DEMO-PAYER",
        plan_code="PLAN-GOLD",
        service_date=date(2026, 9, 1),
    )
    assert results
    assert results[0].policy_code == "POL-AUTH-001"
    assert results[0].source_uri == "synthetic://policies/POL-AUTH-001"


def test_wrong_plan_never_leaks_policy(session):
    results = search_policies(
        session,
        query="prior authorization",
        payer_code="DEMO-PAYER",
        plan_code="OTHER-PLAN",
        service_date=date(2026, 9, 1),
    )
    assert results == []
