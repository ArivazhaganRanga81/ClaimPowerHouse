from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Claim, PublicationState, Rule, RuleResult, RuleVersion


@dataclass(frozen=True)
class Evaluation:
    passed: bool
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)


RuleFunction = Callable[[Session, Claim, dict[str, Any]], Evaluation]


def required_fields(_: Session, claim: Claim, __: dict[str, Any]) -> Evaluation:
    missing: list[str] = []
    if not claim.diagnoses:
        missing.append("diagnosis")
    if not claim.lines:
        missing.append("claim_lines")
    for line in claim.lines:
        if not line.procedure_code:
            missing.append(f"line[{line.line_number}].procedure_code")
    return Evaluation(
        passed=not missing,
        message="All required claim fields are present."
        if not missing
        else "Required fields are missing.",
        evidence={"missing_fields": missing},
    )


def unit_limit(_: Session, claim: Claim, parameters: dict[str, Any]) -> Evaluation:
    violations = []
    for line in claim.lines:
        maximum = parameters.get(line.procedure_code)
        if maximum is not None and line.units > int(maximum):
            violations.append(
                {
                    "line_number": line.line_number,
                    "procedure_code": line.procedure_code,
                    "submitted_units": line.units,
                    "maximum_units": int(maximum),
                }
            )
    return Evaluation(
        passed=not violations,
        message="Units are within policy limits."
        if not violations
        else "Units exceed policy limits.",
        evidence={"violations": violations},
    )


def authorization(_: Session, claim: Claim, parameters: dict[str, Any]) -> Evaluation:
    missing = [
        {"line_number": line.line_number, "procedure_code": line.procedure_code}
        for line in claim.lines
        if parameters.get(line.procedure_code) and not line.authorization_number
    ]
    return Evaluation(
        passed=not missing,
        message="Required authorization is present."
        if not missing
        else "Required authorization is missing.",
        evidence={"missing_authorizations": missing},
    )


def code_pair(_: Session, claim: Claim, __: dict[str, Any]) -> Evaluation:
    violations = [
        {
            "line_number": line.line_number,
            "procedure_code": line.procedure_code,
            "required_modifier": "59",
        }
        for line in claim.lines
        if line.procedure_code == "93000" and line.units > 1 and "59" not in line.modifiers
    ]
    return Evaluation(
        passed=not violations,
        message="Code and modifier combinations are valid."
        if not violations
        else "A required modifier is missing.",
        evidence={"violations": violations},
    )


def duplicate(session: Session, claim: Claim, __: dict[str, Any]) -> Evaluation:
    procedure_codes = {line.procedure_code for line in claim.lines}
    candidates = session.scalars(
        select(Claim).where(
            Claim.id != claim.id,
            Claim.member_id == claim.member_id,
            Claim.provider_id == claim.provider_id,
            Claim.service_start == claim.service_start,
        )
    ).all()
    matches = [
        candidate.external_claim_id
        for candidate in candidates
        if procedure_codes.intersection({line.procedure_code for line in candidate.lines})
    ]
    return Evaluation(
        passed=not matches,
        message="No duplicate claim was found."
        if not matches
        else "Potential duplicate claim found.",
        evidence={"matching_claim_ids": matches},
    )


REGISTRY: dict[str, RuleFunction] = {
    "required_fields": required_fields,
    "unit_limit": unit_limit,
    "authorization": authorization,
    "code_pair": code_pair,
    "duplicate": duplicate,
}


def active_rule_versions(session: Session, service_date: date) -> list[tuple[Rule, RuleVersion]]:
    statement = (
        select(Rule, RuleVersion)
        .join(RuleVersion, RuleVersion.rule_id == Rule.id)
        .where(
            Rule.active.is_(True),
            RuleVersion.state == PublicationState.ACTIVE,
            RuleVersion.effective_from <= service_date,
            (RuleVersion.effective_to.is_(None) | (RuleVersion.effective_to >= service_date)),
        )
        .order_by(Rule.code)
    )
    return list(session.execute(statement).all())


def run_rules(session: Session, claim: Claim, job_id: str) -> list[RuleResult]:
    results: list[RuleResult] = []
    for rule, version in active_rule_versions(session, claim.service_start):
        function = REGISTRY.get(rule.implementation_key)
        if function is None:
            evaluation = Evaluation(
                False, "Rule implementation is unavailable.", {"configuration_error": True}
            )
        else:
            evaluation = function(session, claim, version.parameters)
        result = RuleResult(
            job_id=job_id,
            claim_id=claim.id,
            rule_version_id=version.id,
            passed=evaluation.passed,
            severity=rule.severity,
            message=evaluation.message,
            evidence={"rule_code": rule.code, **evaluation.evidence},
        )
        session.add(result)
        results.append(result)
    session.flush()
    return results
