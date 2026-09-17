export type ClaimStatus = "NEW" | "NEEDS_REVIEW" | "PENDED" | "APPROVED" | "DENIED" | "CANCELLED";

export interface ClaimSummary {
  id: string;
  external_claim_id: string;
  payer_code: string;
  plan_code: string;
  claim_type: string;
  status: ClaimStatus;
  currency: string;
  billed_amount_minor: number;
  service_start: string;
  service_end: string;
  received_at: string;
  assigned_to: string | null;
  risk_score: number;
  version: number;
}

export interface ClaimLine {
  id: string;
  line_number: number;
  procedure_code: string;
  modifiers: string[];
  units: number;
  billed_amount_minor: number;
  allowed_amount_minor: number | null;
  authorization_number: string | null;
  status: string;
}

export interface ClaimDetail extends ClaimSummary {
  allowed_amount_minor: number | null;
  paid_amount_minor: number | null;
  member: { id: string; external_id: string; display_name: string; birth_date: string; sex: string };
  provider: { id: string; external_id: string; display_name: string; specialty: string };
  lines: ClaimLine[];
  diagnoses: Array<{ id: string; code_system: string; code: string; sequence: number }>;
}

export interface ClaimPage { items: ClaimSummary[]; total: number; limit: number; offset: number }

export interface Job {
  id: string;
  claim_id: string;
  claim_version: number;
  status: "QUEUED" | "RUNNING" | "WAITING_FOR_HUMAN" | "COMPLETED" | "FAILED" | "CANCELLED";
  correlation_id: string;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface Finding {
  id: string;
  agent_run_id: string;
  finding_type: string;
  severity: string;
  conclusion: string;
  confidence_milli: number;
  reason_codes: string[];
  evidence: Array<Record<string, unknown>>;
  recommended_action: string | null;
  limitations: string[];
}

export interface Recommendation {
  id: string;
  job_id: string;
  status: string;
  recommended_action: string;
  summary: string;
  reason_codes: string[];
  finding_ids: string[];
  evidence: Array<Record<string, unknown>>;
  suggested_edits: Array<Record<string, unknown>>;
  missing_evidence: string[];
  adjudicator_note: string;
  requires_human_review: boolean;
  synthesis_provider: string | null;
  synthesis_model: string | null;
  synthesis_status: string | null;
  synthesis_error: string | null;
}

export interface TraceEvent { id: number; type: string; created_at: string; payload: Record<string, unknown> }

export interface Policy {
  id: string;
  policy_code: string;
  title: string;
  payer_code: string;
  plan_code: string;
  jurisdiction: string;
  source_uri: string | null;
  created_at: string;
  updated_at: string;
}

export interface PolicyVersion {
  id: string;
  policy_id: string;
  version: string;
  content: string;
  effective_from: string;
  effective_to: string | null;
  state: "DRAFT" | "TESTED" | "APPROVED" | "ACTIVE" | "RETIRED";
  content_hash: string;
  created_at: string;
  updated_at: string;
}

export interface PolicyEvidence {
  chunk_id: string;
  policy_code: string;
  policy_version: string;
  title: string;
  heading_path: string;
  excerpt: string;
  effective_from: string;
  effective_to: string | null;
  score: number;
  source_uri: string | null;
}

export interface ClaimEnquiryResponse {
  answer: string;
  provider: string;
  model: string;
  citations: PolicyEvidence[];
}
