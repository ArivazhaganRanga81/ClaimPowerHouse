from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    Claim,
    ClaimDiagnosis,
    ClaimLine,
    ClaimStatus,
    Member,
    PolicyChunk,
    PolicyDocument,
    PolicyVersion,
    Provider,
    PublicationState,
    Rule,
    RuleVersion,
    User,
)
from ..security import hash_password

SEED_NAMESPACE = uuid.UUID("496f2a40-16f0-4dfa-86f7-60768fdb8811")


def sid(name: str) -> str:
    return uuid.uuid5(SEED_NAMESPACE, name).hex


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def seed_demo(session: Session) -> int:
    if (session.scalar(select(func.count()).select_from(Claim)) or 0) > 0:
        for user_id, password in (
            (sid("user-adjudicator"), "DemoOnly!2026"),
            (sid("user-admin"), "DemoAdminOnly!2026"),
        ):
            user = session.get(User, user_id)
            if user is not None and not user.password_hash:
                user.password_hash = hash_password(password)
        session.commit()
        return 0

    adjudicator = User(
        id=sid("user-adjudicator"),
        email="adjudicator@example.invalid",
        display_name="Demo Adjudicator",
        role="ADJUDICATOR",
        password_hash=hash_password("DemoOnly!2026"),
    )
    admin = User(
        id=sid("user-admin"),
        email="admin@example.invalid",
        display_name="Demo Administrator",
        role="ADMINISTRATOR",
        password_hash=hash_password("DemoAdminOnly!2026"),
    )
    session.add_all([adjudicator, admin])

    members = [
        Member(
            id=sid(f"member-{i}"),
            external_id=f"SYN-M-{i:04d}",
            display_name=f"Synthetic Member {i:02d}",
            birth_date=date(1970 + i % 35, (i % 12) + 1, (i % 27) + 1),
            sex="X" if i % 3 == 0 else ("F" if i % 2 == 0 else "M"),
        )
        for i in range(1, 31)
    ]
    providers = [
        Provider(
            id=sid(f"provider-{i}"),
            external_id=f"SYN-P-{i:04d}",
            display_name=f"Synthetic Provider Group {i:02d}",
            specialty="Internal Medicine" if i % 2 else "Orthopedics",
        )
        for i in range(1, 13)
    ]
    session.add_all([*members, *providers])

    policy_specs = [
        (
            "POL-UNIT-001",
            "Professional Service Unit Limits",
            "# Unit limits\nProcedure 99215 is limited to 5 units per date of service. "
            "Claims above the limit require correction and review.",
            "Coverage > Unit limits",
        ),
        (
            "POL-AUTH-001",
            "Prior Authorization Requirements",
            "# Authorization\nProcedure 27447 requires valid prior authorization for PLAN-GOLD. "
            "If authorization documentation is absent, pend the claim and request it.",
            "Coverage > Prior authorization",
        ),
        (
            "POL-MOD-001",
            "Procedure Modifier Policy",
            "# Modifiers\nProcedure 93000 billed more than once on the same service date requires "
            "modifier 59 when the services are distinct.",
            "Coding > Modifiers",
        ),
    ]
    for code, title, content, heading in policy_specs:
        document = PolicyDocument(
            id=sid(f"policy-{code}"),
            policy_code=code,
            title=title,
            payer_code="DEMO-PAYER",
            plan_code="PLAN-GOLD",
            jurisdiction="DEMO",
            source_uri=f"synthetic://policies/{code}",
        )
        version = PolicyVersion(
            id=sid(f"policy-version-{code}-1"),
            policy_id=document.id,
            version="1.0",
            content=content,
            effective_from=date(2026, 1, 1),
            effective_to=None,
            state=PublicationState.ACTIVE,
            content_hash=sha(content),
        )
        chunk = PolicyChunk(
            id=sid(f"policy-chunk-{code}-1"),
            policy_version_id=version.id,
            ordinal=1,
            heading_path=heading,
            text=content.replace("# ", ""),
            content_hash=sha(content.replace("# ", "")),
            chroma_id=sid(f"policy-chunk-{code}-1"),
        )
        session.add_all([document, version, chunk])

    rules = [
        ("REQ_FIELD_001", "Required claim fields", "required_fields", "HIGH", {}),
        ("UNIT_LIMIT_001", "Procedure unit limits", "unit_limit", "HIGH", {"99215": 5}),
        ("AUTH_001", "Prior authorization", "authorization", "HIGH", {"27447": True}),
        ("CODE_PAIR_001", "Code and modifier compatibility", "code_pair", "MEDIUM", {}),
        ("DUP_CLAIM_001", "Duplicate claim", "duplicate", "HIGH", {}),
    ]
    for code, name, key, severity, parameters in rules:
        rule = Rule(
            id=sid(f"rule-{code}"),
            code=code,
            name=name,
            category="CLAIM_REVIEW",
            severity=severity,
            implementation_key=key,
            active=True,
        )
        version_text = f"{code}:1.0:{parameters}"
        version = RuleVersion(
            id=sid(f"rule-version-{code}-1"),
            rule_id=rule.id,
            version="1.0",
            parameters=parameters,
            explanation_template=name,
            effective_from=date(2026, 1, 1),
            effective_to=None,
            state=PublicationState.ACTIVE,
            content_hash=sha(version_text),
        )
        session.add_all([rule, version])

    today = datetime.now(UTC)
    for i in range(1, 21):
        procedure = "99215"
        units = 1
        authorization = None
        modifiers: list[str] = []
        risk = 10
        if i in {2, 7, 14}:
            units = 8
            risk = 70
        if i in {3, 8, 15}:
            procedure = "27447"
            risk = 85
        elif i in {4, 9}:
            procedure = "27447"
            authorization = f"SYN-AUTH-{i:04d}"
            risk = 20
        elif i in {5, 10}:
            procedure = "93000"
            units = 2
            risk = 55
        claim = Claim(
            id=sid(f"claim-{i}"),
            external_claim_id=f"SYN-C-{i:05d}",
            member_id=members[(i - 1) % len(members)].id,
            provider_id=providers[(i - 1) % len(providers)].id,
            payer_code="DEMO-PAYER",
            plan_code="PLAN-GOLD",
            status=ClaimStatus.NEW,
            billed_amount_minor=12_500 + i * 725,
            service_start=date(2026, 9, 1) - timedelta(days=i),
            service_end=date(2026, 9, 1) - timedelta(days=i),
            received_at=today - timedelta(hours=i * 3),
            assigned_to=adjudicator.id if i % 2 else None,
            risk_score=risk,
        )
        line = ClaimLine(
            id=sid(f"claim-line-{i}-1"),
            claim_id=claim.id,
            line_number=1,
            procedure_code=procedure,
            modifiers=modifiers,
            units=units,
            billed_amount_minor=claim.billed_amount_minor,
            authorization_number=authorization,
        )
        diagnosis = ClaimDiagnosis(
            id=sid(f"claim-diagnosis-{i}-1"),
            claim_id=claim.id,
            code="M17.11" if procedure == "27447" else "Z00.00",
            sequence=1,
        )
        session.add_all([claim, line, diagnosis])

    session.commit()
    return 20
