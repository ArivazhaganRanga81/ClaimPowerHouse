from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import ClaimStatus, JobStatus, RecommendationStatus


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MemberView(ApiModel):
    id: str
    external_id: str
    display_name: str
    birth_date: date
    sex: str


class ProviderView(ApiModel):
    id: str
    external_id: str
    display_name: str
    specialty: str


class ClaimLineView(ApiModel):
    id: str
    line_number: int
    procedure_code: str
    modifiers: list[str]
    units: int
    billed_amount_minor: int
    allowed_amount_minor: int | None
    authorization_number: str | None
    status: str


class DiagnosisView(ApiModel):
    id: str
    code_system: str
    code: str
    sequence: int


class ClaimSummary(ApiModel):
    id: str
    external_claim_id: str
    payer_code: str
    plan_code: str
    claim_type: str
    status: ClaimStatus
    currency: str
    billed_amount_minor: int
    service_start: date
    service_end: date
    received_at: datetime
    assigned_to: str | None
    risk_score: int
    version: int


class ClaimDetail(ClaimSummary):
    allowed_amount_minor: int | None
    paid_amount_minor: int | None
    member: MemberView
    provider: ProviderView
    lines: list[ClaimLineView]
    diagnoses: list[DiagnosisView]


class ClaimPage(ApiModel):
    items: list[ClaimSummary]
    total: int
    limit: int
    offset: int


class StartAdjudicationRequest(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=100)


class JobView(ApiModel):
    id: str
    claim_id: str
    claim_version: int
    status: JobStatus
    correlation_id: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class FindingView(ApiModel):
    id: str
    job_id: str
    agent_run_id: str
    finding_type: str
    severity: str
    conclusion: str
    confidence_milli: int
    reason_codes: list[str]
    evidence: list[dict[str, Any]]
    recommended_action: str | None
    limitations: list[str]
    schema_version: str
    created_at: datetime


class RecommendationView(ApiModel):
    id: str
    job_id: str
    claim_id: str
    status: RecommendationStatus
    recommended_action: str
    summary: str
    reason_codes: list[str]
    finding_ids: list[str]
    evidence: list[dict[str, Any]]
    suggested_edits: list[dict[str, Any]]
    missing_evidence: list[str]
    adjudicator_note: str
    requires_human_review: bool
    schema_version: str
    synthesis_provider: str | None = None
    synthesis_model: str | None = None
    synthesis_status: str | None = None
    synthesis_error: str | None = None


class ClaimEnquiryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)


class ClaimEnquiryResponse(BaseModel):
    answer: str
    provider: str
    model: str
    citations: list[dict[str, Any]]


Disposition = Literal["APPROVED", "DENIED", "PENDED", "NEEDS_REVIEW"]
RecommendationResponse = Literal["ACCEPTED", "MODIFIED", "REJECTED"]


class SubmitDecisionRequest(BaseModel):
    job_id: str | None = None
    recommendation_id: str | None = None
    recommendation_response: RecommendationResponse | None = None
    disposition: Disposition
    expected_claim_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=100)
    override_reason: str | None = Field(default=None, max_length=1000)
    note: str | None = Field(default=None, max_length=4000)
    attested: bool


class DecisionView(ApiModel):
    id: str
    claim_id: str
    disposition: str
    expected_claim_version: int
    override_reason: str | None
    note: str | None
    attested: bool
    created_at: datetime


class AuditEventView(ApiModel):
    id: str
    sequence: int
    actor_id: str | None
    actor_type: str
    claim_id: str | None
    correlation_id: str
    event_type: str
    before_data: dict[str, Any] | None
    after_data: dict[str, Any] | None
    details: dict[str, Any]
    previous_hash: str | None
    event_hash: str
    created_at: datetime


class PolicySearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    payer_code: str
    plan_code: str
    service_date: date
    limit: int = Field(default=5, ge=1, le=20)


class PolicyEvidence(BaseModel):
    chunk_id: str
    policy_code: str
    policy_version: str
    title: str
    heading_path: str
    excerpt: str
    effective_from: date
    effective_to: date | None
    score: float
    source_uri: str | None


class HealthView(BaseModel):
    status: Literal["ok", "degraded"]
    service: str = "claim-power-house"
    version: str
    demo_mode: bool


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=200)


class UserView(BaseModel):
    id: str
    email: str
    display_name: str
    role: str


class CreatePolicyRequest(BaseModel):
    policy_code: str = Field(pattern=r"^[A-Z0-9_-]{3,80}$")
    title: str = Field(min_length=3, max_length=240)
    payer_code: str = Field(min_length=2, max_length=50)
    plan_code: str = Field(min_length=2, max_length=50)
    jurisdiction: str = Field(default="DEMO", max_length=60)
    source_uri: str | None = Field(default=None, max_length=500)


class CreatePolicyVersionRequest(BaseModel):
    version: str = Field(min_length=1, max_length=40)
    content: str = Field(min_length=10, max_length=1_000_000)
    effective_from: date
    effective_to: date | None = None


class UpdatePolicyVersionRequest(BaseModel):
    content: str = Field(min_length=10, max_length=1_000_000)
    effective_from: date
    effective_to: date | None = None


class PolicyVersionView(ApiModel):
    id: str
    policy_id: str
    version: str
    content: str
    effective_from: date
    effective_to: date | None
    state: str
    content_hash: str
    created_at: datetime
    updated_at: datetime


class PolicyView(ApiModel):
    id: str
    policy_code: str
    title: str
    payer_code: str
    plan_code: str
    jurisdiction: str
    source_uri: str | None
    created_at: datetime
    updated_at: datetime


class ImportClaimLine(BaseModel):
    procedure_code: str = Field(min_length=1, max_length=20)
    modifiers: list[str] = Field(default_factory=list, max_length=4)
    units: int = Field(default=1, ge=1, le=10000)
    billed_amount_minor: int = Field(ge=0)
    authorization_number: str | None = Field(default=None, max_length=80)


class ImportClaim(BaseModel):
    external_claim_id: str = Field(min_length=1, max_length=80)
    member_external_id: str = Field(min_length=1, max_length=80)
    provider_external_id: str = Field(min_length=1, max_length=80)
    payer_code: str = Field(min_length=1, max_length=50)
    plan_code: str = Field(min_length=1, max_length=50)
    service_start: date
    service_end: date
    diagnoses: list[str] = Field(min_length=1, max_length=20)
    lines: list[ImportClaimLine] = Field(min_length=1, max_length=100)


class ImportClaimsRequest(BaseModel):
    source_type: str = Field(default="CPH_JSON", max_length=60)
    claims: list[ImportClaim] = Field(min_length=1, max_length=1000)
