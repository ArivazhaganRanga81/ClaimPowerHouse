import { useCallback, useEffect, useMemo, useState } from "react";
import { api, eventsUrl } from "./api";
import { Knowledge } from "./Knowledge";
import type { ClaimDetail, ClaimSummary, Finding, Job, PolicyEvidence, Recommendation, TraceEvent } from "./types";

interface EnquiryMessage {
  role: "user" | "assistant";
  text: string;
  citations?: PolicyEvidence[];
  provider?: string;
  model?: string;
}

const money = (minor: number, currency = "USD") =>
  new Intl.NumberFormat("en-US", { style: "currency", currency }).format(minor / 100);

const dateTime = (value: string) => new Intl.DateTimeFormat("en-US", {
  dateStyle: "medium",
  timeStyle: "short"
}).format(new Date(value));

function statusClass(status: string) {
  return `status status-${status.toLowerCase().replaceAll("_", "-")}`;
}

export function App() {
  const [claims, setClaims] = useState<ClaimSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string>();
  const [claim, setClaim] = useState<ClaimDetail>();
  const [job, setJob] = useState<Job>();
  const [findings, setFindings] = useState<Finding[]>([]);
  const [recommendation, setRecommendation] = useState<Recommendation>();
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [overrideReason, setOverrideReason] = useState("");
  const [question, setQuestion] = useState("");
  const [enquiryBusy, setEnquiryBusy] = useState(false);
  const [messages, setMessages] = useState<EnquiryMessage[]>([]);
  const [showKnowledge, setShowKnowledge] = useState(false);
  const requestedClaimId = useMemo(
    () => new URLSearchParams(window.location.search).get("claim_id") ?? undefined,
    []
  );

  const loadClaims = useCallback(async () => {
    try {
      const page = await api.claims();
      setClaims(page.items);
      setSelectedId((current) => current ?? requestedClaimId ?? page.items[0]?.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  }, [requestedClaimId]);

  useEffect(() => { void loadClaims(); }, [loadClaims]);

  useEffect(() => {
    if (!selectedId) return;
    setError(undefined);
    void api.claim(selectedId).then(setClaim).catch((cause) => setError(String(cause)));
    setJob(undefined);
    setFindings([]);
    setRecommendation(undefined);
    setEvents([]);
    setMessages([]);
    setQuestion("");
    setNotice(undefined);
  }, [selectedId]);

  const loadOutcome = useCallback(async (jobId: string) => {
    const [nextJob, nextFindings, nextRecommendation] = await Promise.all([
      api.job(jobId), api.findings(jobId), api.recommendation(jobId)
    ]);
    setJob(nextJob);
    setFindings(nextFindings);
    setRecommendation(nextRecommendation);
    setBusy(false);
  }, []);

  useEffect(() => {
    if (!job || !["QUEUED", "RUNNING"].includes(job.status)) return;
    const source = new EventSource(eventsUrl(job.id));
    source.onmessage = (event) => {
      const parsed = JSON.parse(event.data) as Omit<TraceEvent, "id">;
      setEvents((current) => [...current, { ...parsed, id: Number(event.lastEventId) }]);
      if (parsed.type === "HUMAN_REVIEW_REQUIRED") {
        source.close();
        void loadOutcome(job.id).catch((cause) => setError(String(cause)));
      }
    };
    source.onerror = () => {
      source.close();
      void api.job(job.id).then((current) => {
        setJob(current);
        if (current.status === "WAITING_FOR_HUMAN") void loadOutcome(job.id);
        else if (current.status === "FAILED") {
          setBusy(false);
          setError(current.error_message ?? "Review failed safely.");
        }
      });
    };
    return () => source.close();
  }, [job?.id, job?.status, loadOutcome]);

  async function runReview() {
    if (!claim) return;
    setBusy(true);
    setError(undefined);
    setNotice("Review started. Deterministic checks run first, followed by AI synthesis.");
    setFindings([]);
    setRecommendation(undefined);
    setEvents([]);
    try {
      setJob(await api.startReview(claim.id));
    } catch (cause) {
      setBusy(false);
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  }

  async function askQuestion(preset?: string) {
    if (!claim) return;
    const nextQuestion = (preset ?? question).trim();
    if (!nextQuestion) return;
    setEnquiryBusy(true);
    setError(undefined);
    setMessages((current) => [...current, { role: "user", text: nextQuestion }]);
    setQuestion("");
    try {
      const response = await api.enquire(claim.id, nextQuestion);
      setMessages((current) => [...current, {
        role: "assistant",
        text: response.answer,
        citations: response.citations,
        provider: response.provider,
        model: response.model
      }]);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setEnquiryBusy(false);
    }
  }

  const suggestedDisposition = useMemo(() => {
    if (recommendation?.recommended_action === "APPROVE_REVIEW") return "APPROVED" as const;
    if (recommendation?.recommended_action === "PEND_REQUEST_DOCUMENTATION") return "PENDED" as const;
    return "NEEDS_REVIEW" as const;
  }, [recommendation]);

  async function decide(response: "ACCEPTED" | "MODIFIED" | "REJECTED") {
    if (!claim || !job || !recommendation) return;
    if (job.status !== "WAITING_FOR_HUMAN" || job.claim_version !== claim.version) {
      setError("This review is stale. The claim was refreshed; run a new review if needed.");
      setClaim(await api.claim(claim.id));
      setJob(undefined);
      setRecommendation(undefined);
      setFindings([]);
      return;
    }
    if (response !== "ACCEPTED" && !overrideReason.trim()) {
      setError("Explain why you are modifying or rejecting the recommendation.");
      return;
    }
    setBusy(true);
    try {
      await api.decide(claim.id, {
        job_id: job.id,
        recommendation_id: recommendation.id,
        recommendation_response: response,
        disposition: response === "ACCEPTED" ? suggestedDisposition : "NEEDS_REVIEW",
        expected_claim_version: claim.version,
        idempotency_key: crypto.randomUUID(),
        override_reason: overrideReason || undefined,
        note: recommendation.adjudicator_note,
        attested: true
      });
      await loadClaims();
      setClaim(await api.claim(claim.id));
      setJob(undefined);
      setRecommendation(undefined);
      setFindings([]);
      setEvents([]);
      setOverrideReason("");
      setNotice(`Decision saved: ${response.toLowerCase()}.`);
      setBusy(false);
    } catch (cause) {
      setBusy(false);
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">HUMAN-IN-THE-LOOP CLAIM REVIEW</p>
          <h1>Claim Power House</h1>
        </div>
        <div className="header-actions">
          <button onClick={() => setShowKnowledge(false)}>Claims</button>
          <button onClick={() => setShowKnowledge(true)}>Policies &amp; RAG</button>
          <div className="demo-warning">Synthetic demo · Not for clinical or payment use</div>
        </div>
      </header>

      {error && <div className="error-banner" role="alert">{error}</div>}
      {notice && <div className="status-banner global-status" role="status">{notice}</div>}

      {showKnowledge ? <Knowledge /> : <main className="workspace">
        <aside className="queue" aria-label="Claims queue">
          <div className="panel-title"><h2>Exception queue</h2><span>{claims.length}</span></div>
          <div className="claim-list">
            {claims.map((item) => (
              <button
                className={`claim-row ${item.id === selectedId ? "selected" : ""}`}
                key={item.id}
                onClick={() => setSelectedId(item.id)}
              >
                <span><strong>{item.external_claim_id}</strong><small>{item.payer_code}</small></span>
                <span className="claim-meta">
                  <span className={statusClass(item.status)}>{item.status.replaceAll("_", " ")}</span>
                  <small>{money(item.billed_amount_minor, item.currency)}</small>
                </span>
              </button>
            ))}
          </div>
        </aside>

        <section className="review">
          {!claim ? <div className="empty">Select a claim to begin.</div> : <>
            <div className="claim-header">
              <div>
                <p className="eyebrow">CLAIM {claim.external_claim_id}</p>
                <h2>{claim.member.display_name}</h2>
                <p>{claim.provider.display_name} · {claim.provider.specialty}</p>
              </div>
              <div className="claim-total"><small>Billed</small><strong>{money(claim.billed_amount_minor)}</strong></div>
              <button className="primary" onClick={() => void runReview()} disabled={busy || claim.status === "APPROVED" || claim.status === "DENIED"}>
                {busy ? "Agents working…" : "Run multi-agent review"}
              </button>
            </div>

            <div className="summary-grid">
              <Info label="Status" value={claim.status.replaceAll("_", " ")} />
              <Info label="Service date" value={claim.service_start} />
              <Info label="Plan" value={claim.plan_code} />
              <Info label="Risk score" value={`${claim.risk_score}/100`} />
            </div>

            <section className="card">
              <div className="panel-title"><h3>Claim lines</h3><span>{claim.lines.length}</span></div>
              <table>
                <thead><tr><th>Line</th><th>Procedure</th><th>Modifier</th><th>Units</th><th>Authorization</th><th>Billed</th></tr></thead>
                <tbody>{claim.lines.map((line) => <tr key={line.id}>
                  <td>{line.line_number}</td><td>{line.procedure_code}</td><td>{line.modifiers.join(", ") || "—"}</td>
                  <td>{line.units}</td><td>{line.authorization_number ?? "Missing"}</td><td>{money(line.billed_amount_minor)}</td>
                </tr>)}</tbody>
              </table>
            </section>

            <section className="card enquiry">
              <div className="panel-title">
                <div><p className="eyebrow">CLAIM ENQUIRY</p><h3>Ask about this claim</h3></div>
                <span>OpenAI + claim evidence</span>
              </div>
              <div className="quick-questions">
                {["Why is this claim flagged?", "What documentation is missing?", "Which policy applies?", "Summarize the key risks."].map((item) =>
                  <button key={item} disabled={enquiryBusy} onClick={() => void askQuestion(item)}>{item}</button>
                )}
              </div>
              {messages.length > 0 && <div className="conversation" aria-live="polite">
                {messages.map((message, index) => <article className={`message message-${message.role}`} key={index}>
                  <strong>{message.role === "user" ? "You" : "AI council"}</strong>
                  <p>{message.text}</p>
                  {message.provider && <small>{message.provider} · {message.model}</small>}
                  {message.citations && message.citations.length > 0 && <div className="message-citations">
                    {message.citations.map((item) => <small key={item.chunk_id}>{item.policy_code} v{item.policy_version}</small>)}
                  </div>}
                </article>)}
              </div>}
              <div className="enquiry-input">
                <textarea value={question} onChange={(event) => setQuestion(event.target.value)} rows={2} placeholder="Ask a claim-specific question…" />
                <button className="primary" disabled={enquiryBusy || !question.trim()} onClick={() => void askQuestion()}>
                  {enquiryBusy ? "Thinking…" : "Ask"}
                </button>
              </div>
            </section>

            {(events.length > 0 || job) && <section className="card trace">
              <div className="panel-title"><h3>Agent trace</h3>{job && <span className={statusClass(job.status)}>{job.status.replaceAll("_", " ")}</span>}</div>
              <ol>{events.map((event) => <li key={`${event.id}-${event.type}`}><span className="trace-dot"/><div><strong>{event.type.replaceAll("_", " ")}</strong><small>{dateTime(event.created_at)}</small></div></li>)}</ol>
            </section>}

            {findings.length > 0 && <section className="card">
              <div className="panel-title"><h3>Specialist findings</h3><span>{findings.length}</span></div>
              <div className="finding-grid">{findings.map((finding) => <article className="finding" key={finding.id}>
                <div><span className={`severity severity-${finding.severity.toLowerCase()}`}>{finding.severity}</span><small>{finding.finding_type}</small></div>
                <h4>{finding.conclusion}</h4>
                <p>{finding.reason_codes.join(" · ")}</p>
                <small>Reported confidence: {Math.round(finding.confidence_milli / 10)}%</small>
              </article>)}</div>
            </section>}

            {recommendation && <section className="recommendation">
              <p className="eyebrow">SYNTHESIS · HUMAN REVIEW REQUIRED</p>
              <h3>{recommendation.recommended_action.replaceAll("_", " ")}</h3>
              <p><strong>AI council:</strong> {recommendation.synthesis_provider ?? "unknown"} · {recommendation.synthesis_model ?? "unknown"} · {recommendation.synthesis_status ?? "unknown"}</p>
              {recommendation.synthesis_error && <p className="error-banner">AI synthesis degraded safely: {recommendation.synthesis_error}</p>}
              <p>{recommendation.summary}</p>
              {recommendation.evidence.length > 0 && <div className="citations">
                <h4>Policy evidence</h4>
                {recommendation.evidence.map((item, index) => <blockquote key={index}>
                  <strong>{String(item.title ?? "Policy")}</strong>
                  <p>{String(item.excerpt ?? "")}</p>
                  <cite>{String(item.policy_code ?? "")} · version {String(item.policy_version ?? "")}</cite>
                </blockquote>)}
              </div>}
              <label className="override">Override reason (required when modifying or rejecting)
                <textarea value={overrideReason} onChange={(event) => setOverrideReason(event.target.value)} rows={3}/>
              </label>
              <div className="actions">
                <button className="primary" disabled={busy || job?.status !== "WAITING_FOR_HUMAN" || job.claim_version !== claim?.version} onClick={() => void decide("ACCEPTED")}>Accept and {suggestedDisposition.toLowerCase().replaceAll("_", " ")}</button>
                <button disabled={busy || job?.status !== "WAITING_FOR_HUMAN" || job.claim_version !== claim?.version} onClick={() => void decide("MODIFIED")}>Modify</button>
                <button className="danger" disabled={busy || job?.status !== "WAITING_FOR_HUMAN" || job.claim_version !== claim?.version} onClick={() => void decide("REJECTED")}>Reject</button>
              </div>
            </section>}
          </>}
        </section>
      </main>}
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return <div className="info"><small>{label}</small><strong>{value}</strong></div>;
}
