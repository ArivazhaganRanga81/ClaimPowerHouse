from __future__ import annotations
import hashlib
import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import AuditEvent


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def append_audit_event(
    session: Session,
    *,
    actor_id: str | None,
    actor_type: str,
    claim_id: str | None,
    correlation_id: str,
    event_type: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    previous = session.scalar(select(AuditEvent).order_by(AuditEvent.sequence.desc()).limit(1))
    sequence = (previous.sequence + 1) if previous else 1
    previous_hash = previous.event_hash if previous else None
    body = {
        "sequence": sequence,
        "actor_id": actor_id,
        "actor_type": actor_type,
        "claim_id": claim_id,
        "correlation_id": correlation_id,
        "event_type": event_type,
        "before": before,
        "after": after,
        "details": details or {},
        "previous_hash": previous_hash,
    }
    event_hash = hashlib.sha256(canonical_json(body).encode()).hexdigest()
    event = AuditEvent(
        sequence=sequence,
        actor_id=actor_id,
        actor_type=actor_type,
        claim_id=claim_id,
        correlation_id=correlation_id,
        event_type=event_type,
        before_data=before,
        after_data=after,
        details=details or {},
        previous_hash=previous_hash,
        event_hash=event_hash,
    )
    session.add(event)
    session.flush()
    return event


def verify_audit_chain(session: Session) -> tuple[bool, int]:
    events = session.scalars(select(AuditEvent).order_by(AuditEvent.sequence)).all()
    previous_hash: str | None = None
    for event in events:
        body = {
            "sequence": event.sequence,
            "actor_id": event.actor_id,
            "actor_type": event.actor_type,
            "claim_id": event.claim_id,
            "correlation_id": event.correlation_id,
            "event_type": event.event_type,
            "before": event.before_data,
            "after": event.after_data,
            "details": event.details,
            "previous_hash": previous_hash,
        }
        expected = hashlib.sha256(canonical_json(body).encode()).hexdigest()
        if event.previous_hash != previous_hash or event.event_hash != expected:
            return False, event.sequence
        previous_hash = event.event_hash
    return True, len(events)


def next_job_event_sequence(session: Session, job_id: str) -> int:
    current = session.scalar(
        select(func.max(AuditEvent.sequence)).where(AuditEvent.claim_id == job_id)
    )
    return (current or 0) + 1
