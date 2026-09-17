import type {
  ClaimDetail,
  ClaimPage,
  Finding,
  Job,
  Policy,
  PolicyEvidence,
  PolicyVersion,
  Recommendation
} from "./types";

const base = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${base}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) }
  });
  if (!response.ok) throw new Error((await response.text()) || response.statusText);
  return response.json() as Promise<T>;
}

export const api = {
  login: (email: string, password: string) => request<{ id: string; role: string; display_name: string }>(
    "/api/v1/auth/login",
    { method: "POST", body: JSON.stringify({ email, password }) }
  ),
  claims: () => request<ClaimPage>("/api/v1/claims"),
  claim: (id: string) => request<ClaimDetail>(`/api/v1/claims/${id}`),
  startReview: (claimId: string) =>
    request<Job>(`/api/v1/claims/${claimId}/adjudications`, {
      method: "POST",
      body: JSON.stringify({ idempotency_key: crypto.randomUUID() })
    }),
  job: (id: string) => request<Job>(`/api/v1/adjudications/${id}`),
  findings: (id: string) => request<Finding[]>(`/api/v1/adjudications/${id}/findings`),
  recommendation: (id: string) =>
    request<Recommendation>(`/api/v1/adjudications/${id}/recommendation`),
  decide: (
    claimId: string,
    body: {
      job_id: string;
      recommendation_id: string;
      recommendation_response: "ACCEPTED" | "MODIFIED" | "REJECTED";
      disposition: "APPROVED" | "DENIED" | "PENDED" | "NEEDS_REVIEW";
      expected_claim_version: number;
      idempotency_key: string;
      override_reason?: string;
      note?: string;
      attested: boolean;
    }
  ) =>
    request(`/api/v1/claims/${claimId}/decisions`, {
      method: "POST",
      body: JSON.stringify(body)
    }),
  policies: () => request<Policy[]>("/api/v1/policies"),
  policyVersions: (policyId: string) =>
    request<PolicyVersion[]>(`/api/v1/policies/${policyId}/versions`),
  createPolicyVersion: (
    policyId: string,
    body: { version: string; content: string; effective_from: string; effective_to: string | null }
  ) => request<PolicyVersion>(`/api/v1/policies/${policyId}/versions`, {
    method: "POST", body: JSON.stringify(body)
  }),
  updatePolicyVersion: (
    versionId: string,
    body: { content: string; effective_from: string; effective_to: string | null }
  ) => request<PolicyVersion>(`/api/v1/policy-versions/${versionId}`, {
    method: "PUT", body: JSON.stringify(body)
  }),
  publishPolicyVersion: (versionId: string) =>
    request<PolicyVersion>(`/api/v1/policy-versions/${versionId}/publish`, { method: "POST" }),
  rebuildIndex: () => request<Record<string, unknown>>("/api/v1/rag/indexes/rebuild", { method: "POST" }),
  testRetrieval: (body: {
    query: string; payer_code: string; plan_code: string; service_date: string; limit: number
  }) => request<PolicyEvidence[]>("/api/v1/rag/query-test", { method: "POST", body: JSON.stringify(body) })
};

export const eventsUrl = (jobId: string) => `${base}/api/v1/adjudications/${jobId}/events`;
