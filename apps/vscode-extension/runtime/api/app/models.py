from __future__ import annotations

import enum
import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def new_id() -> str:
    return uuid.uuid4().hex


def now_utc() -> datetime:
    return datetime.now(UTC)


class ClaimStatus(enum.StrEnum):
    NEW = "NEW"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    PENDED = "PENDED"
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    CANCELLED = "CANCELLED"


class JobStatus(enum.StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_FOR_HUMAN = "WAITING_FOR_HUMAN"
    DEGRADED = "DEGRADED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StepStatus(enum.StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    SKIPPED = "SKIPPED"
    TIMED_OUT = "TIMED_OUT"
    FAILED = "FAILED"


class RecommendationStatus(enum.StrEnum):
    DRAFT = "DRAFT"
    READY = "READY"
    ACCEPTED = "ACCEPTED"
    MODIFIED = "MODIFIED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class PublicationState(enum.StrEnum):
    DRAFT = "DRAFT"
    TESTED = "TESTED"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(32), default="ADJUDICATOR")
    password_hash: Mapped[str | None] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class AuthSession(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Member(Base, TimestampMixin):
    __tablename__ = "members"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    external_id: Mapped[str] = mapped_column(String(80), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    birth_date: Mapped[date] = mapped_column(Date)
    sex: Mapped[str] = mapped_column(String(20))


class Provider(Base, TimestampMixin):
    __tablename__ = "providers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    external_id: Mapped[str] = mapped_column(String(80), unique=True)
    display_name: Mapped[str] = mapped_column(String(180))
    specialty: Mapped[str] = mapped_column(String(120))


class Claim(Base, TimestampMixin):
    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    external_claim_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    member_id: Mapped[str] = mapped_column(ForeignKey("members.id"), index=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), index=True)
    payer_code: Mapped[str] = mapped_column(String(50), index=True)
    plan_code: Mapped[str] = mapped_column(String(50), index=True)
    claim_type: Mapped[str] = mapped_column(String(40), default="PROFESSIONAL")
    status: Mapped[ClaimStatus] = mapped_column(Enum(ClaimStatus), default=ClaimStatus.NEW)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    billed_amount_minor: Mapped[int] = mapped_column(Integer)
    allowed_amount_minor: Mapped[int | None] = mapped_column(Integer)
    paid_amount_minor: Mapped[int | None] = mapped_column(Integer)
    service_start: Mapped[date] = mapped_column(Date)
    service_end: Mapped[date] = mapped_column(Date)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    assigned_to: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)

    member: Mapped[Member] = relationship()
    provider: Mapped[Provider] = relationship()
    lines: Mapped[list[ClaimLine]] = relationship(
        back_populates="claim", cascade="all, delete-orphan", order_by="ClaimLine.line_number"
    )
    diagnoses: Mapped[list[ClaimDiagnosis]] = relationship(
        back_populates="claim", cascade="all, delete-orphan"
    )


class ClaimLine(Base, TimestampMixin):
    __tablename__ = "claim_lines"
    __table_args__ = (UniqueConstraint("claim_id", "line_number"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"), index=True)
    line_number: Mapped[int] = mapped_column(Integer)
    procedure_code: Mapped[str] = mapped_column(String(20), index=True)
    modifiers: Mapped[list[str]] = mapped_column(JSON, default=list)
    units: Mapped[int] = mapped_column(Integer, default=1)
    billed_amount_minor: Mapped[int] = mapped_column(Integer)
    allowed_amount_minor: Mapped[int | None] = mapped_column(Integer)
    authorization_number: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), default="SUBMITTED")

    claim: Mapped[Claim] = relationship(back_populates="lines")


class ClaimDiagnosis(Base):
    __tablename__ = "claim_diagnoses"
    __table_args__ = (UniqueConstraint("claim_id", "sequence"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"), index=True)
    line_id: Mapped[str | None] = mapped_column(ForeignKey("claim_lines.id", ondelete="CASCADE"))
    code_system: Mapped[str] = mapped_column(String(40), default="ICD-10-CM")
    code: Mapped[str] = mapped_column(String(20), index=True)
    sequence: Mapped[int] = mapped_column(Integer)

    claim: Mapped[Claim] = relationship(back_populates="diagnoses")


class Rule(Base, TimestampMixin):
    __tablename__ = "rules"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(60))
    severity: Mapped[str] = mapped_column(String(20))
    implementation_key: Mapped[str] = mapped_column(String(100))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class RuleVersion(Base, TimestampMixin):
    __tablename__ = "rule_versions"
    __table_args__ = (UniqueConstraint("rule_id", "version"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    rule_id: Mapped[str] = mapped_column(ForeignKey("rules.id"), index=True)
    version: Mapped[str] = mapped_column(String(30))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    explanation_template: Mapped[str] = mapped_column(Text)
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    state: Mapped[PublicationState] = mapped_column(Enum(PublicationState))
    content_hash: Mapped[str] = mapped_column(String(64))

    rule: Mapped[Rule] = relationship()


class PolicyDocument(Base, TimestampMixin):
    __tablename__ = "policy_documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    policy_code: Mapped[str] = mapped_column(String(80), unique=True)
    title: Mapped[str] = mapped_column(String(240))
    payer_code: Mapped[str] = mapped_column(String(50), index=True)
    plan_code: Mapped[str] = mapped_column(String(50), index=True)
    jurisdiction: Mapped[str] = mapped_column(String(60), default="DEMO")
    source_uri: Mapped[str | None] = mapped_column(String(500))


class PolicyVersion(Base, TimestampMixin):
    __tablename__ = "policy_versions"
    __table_args__ = (UniqueConstraint("policy_id", "version"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    policy_id: Mapped[str] = mapped_column(ForeignKey("policy_documents.id"), index=True)
    version: Mapped[str] = mapped_column(String(40))
    content: Mapped[str] = mapped_column(Text)
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    state: Mapped[PublicationState] = mapped_column(Enum(PublicationState))
    content_hash: Mapped[str] = mapped_column(String(64))

    policy: Mapped[PolicyDocument] = relationship()
    chunks: Mapped[list[PolicyChunk]] = relationship(
        back_populates="policy_version", cascade="all, delete-orphan"
    )


class PolicyChunk(Base):
    __tablename__ = "policy_chunks"
    __table_args__ = (UniqueConstraint("policy_version_id", "ordinal"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    policy_version_id: Mapped[str] = mapped_column(
        ForeignKey("policy_versions.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    heading_path: Mapped[str] = mapped_column(String(500))
    text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    chroma_id: Mapped[str | None] = mapped_column(String(120))

    policy_version: Mapped[PolicyVersion] = relationship(back_populates="chunks")


class RagIndexVersion(Base, TimestampMixin):
    __tablename__ = "rag_index_versions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    version: Mapped[str] = mapped_column(String(40), unique=True)
    collection_name: Mapped[str] = mapped_column(String(120), unique=True)
    embedding_model: Mapped[str] = mapped_column(String(240))
    chunking_version: Mapped[str] = mapped_column(String(40))
    source_set_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default="BUILDING")
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)


class AdjudicationJob(Base, TimestampMixin):
    __tablename__ = "adjudication_jobs"
    __table_args__ = (UniqueConstraint("requested_by", "idempotency_key"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id"), index=True)
    claim_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.QUEUED)
    idempotency_key: Mapped[str] = mapped_column(String(100))
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    claim_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)


class AgentRun(Base, TimestampMixin):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("adjudication_jobs.id"), index=True)
    agent_type: Mapped[str] = mapped_column(String(60))
    status: Mapped[StepStatus] = mapped_column(Enum(StepStatus), default=StepStatus.PENDING)
    prompt_version: Mapped[str | None] = mapped_column(String(60))
    model_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    input_hash: Mapped[str | None] = mapped_column(String(64))
    output_hash: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)


class AgentFinding(Base):
    __tablename__ = "agent_findings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("adjudication_jobs.id"), index=True)
    agent_run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    finding_type: Mapped[str] = mapped_column(String(100))
    severity: Mapped[str] = mapped_column(String(20))
    conclusion: Mapped[str] = mapped_column(Text)
    confidence_milli: Mapped[int] = mapped_column(Integer)
    reason_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    recommended_action: Mapped[str | None] = mapped_column(String(80))
    limitations: Mapped[list[str]] = mapped_column(JSON, default=list)
    schema_version: Mapped[str] = mapped_column(String(20), default="1.0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Recommendation(Base, TimestampMixin):
    __tablename__ = "recommendations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("adjudication_jobs.id"), unique=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id"), index=True)
    status: Mapped[RecommendationStatus] = mapped_column(
        Enum(RecommendationStatus), default=RecommendationStatus.DRAFT
    )
    recommended_action: Mapped[str] = mapped_column(String(80))
    summary: Mapped[str] = mapped_column(Text)
    reason_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    finding_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    suggested_edits: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    missing_evidence: Mapped[list[str]] = mapped_column(JSON, default=list)
    adjudicator_note: Mapped[str] = mapped_column(Text, default="")
    requires_human_review: Mapped[bool] = mapped_column(Boolean, default=True)
    schema_version: Mapped[str] = mapped_column(String(20), default="1.0")


class LlmCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("adjudication_jobs.id"), index=True)
    provider: Mapped[str] = mapped_column(String(60))
    model: Mapped[str] = mapped_column(String(160))
    prompt_version: Mapped[str] = mapped_column(String(40))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_hash: Mapped[str | None] = mapped_column(String(64))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class RuleResult(Base):
    __tablename__ = "rule_results"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("adjudication_jobs.id"), index=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id"), index=True)
    rule_version_id: Mapped[str] = mapped_column(ForeignKey("rule_versions.id"))
    passed: Mapped[bool] = mapped_column(Boolean)
    severity: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class JobEvent(Base):
    __tablename__ = "job_events"
    __table_args__ = (UniqueConstraint("job_id", "sequence"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("adjudication_jobs.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ClaimDecision(Base):
    __tablename__ = "claim_decisions"
    __table_args__ = (UniqueConstraint("actor_user_id", "idempotency_key"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id"), index=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("adjudication_jobs.id"))
    recommendation_id: Mapped[str | None] = mapped_column(ForeignKey("recommendations.id"))
    disposition: Mapped[str] = mapped_column(String(40))
    actor_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    expected_claim_version: Mapped[int] = mapped_column(Integer)
    override_reason: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    attested: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    sequence: Mapped[int] = mapped_column(Integer, unique=True)
    actor_id: Mapped[str | None] = mapped_column(String(32), index=True)
    actor_type: Mapped[str] = mapped_column(String(30))
    claim_id: Mapped[str | None] = mapped_column(String(32), index=True)
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(100))
    before_data: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after_data: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    previous_hash: Mapped[str | None] = mapped_column(String(64))
    event_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ImportBatch(Base, TimestampMixin):
    __tablename__ = "import_batches"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    source_type: Mapped[str] = mapped_column(String(60))
    source_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(30))
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    imported_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id"))


class BackupRecord(Base):
    __tablename__ = "backups"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    artifact_name: Mapped[str] = mapped_column(String(240), unique=True)
    artifact_hash: Mapped[str] = mapped_column(String(64))
    schema_revision: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(30))
    size_bytes: Mapped[int] = mapped_column(Integer)
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


Index("ix_claim_queue", Claim.status, Claim.received_at)
Index(
    "ix_policy_effective",
    PolicyVersion.state,
    PolicyVersion.effective_from,
    PolicyVersion.effective_to,
)
