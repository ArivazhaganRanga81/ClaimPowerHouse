import { useEffect, useState } from "react";
import { api } from "./api";
import type { Policy, PolicyEvidence, PolicyVersion } from "./types";

export function Knowledge() {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [selected, setSelected] = useState<Policy>();
  const [versions, setVersions] = useState<PolicyVersion[]>([]);
  const [draft, setDraft] = useState<PolicyVersion>();
  const [content, setContent] = useState("");
  const [versionName, setVersionName] = useState("2.0");
  const [effectiveFrom, setEffectiveFrom] = useState("2026-09-17");
  const [query, setQuery] = useState("prior authorization required");
  const [results, setResults] = useState<PolicyEvidence[]>([]);
  const [status, setStatus] = useState<string>();
  const [error, setError] = useState<string>();
  const [credentials, setCredentials] = useState({ email: "admin@example.invalid", password: "" });

  async function loadPolicies() {
    try {
      const items = await api.policies();
      setPolicies(items);
      setSelected((current) => current ?? items[0]);
      setError(undefined);
    } catch (cause) { setError(String(cause)); }
  }

  useEffect(() => { void loadPolicies(); }, []);
  useEffect(() => {
    if (!selected) return;
    void api.policyVersions(selected.id).then((items) => {
      setVersions(items);
      const editable = items.find((item) => item.state === "DRAFT");
      setDraft(editable);
      setContent(editable?.content ?? items[0]?.content ?? "");
    }).catch((cause) => setError(String(cause)));
  }, [selected?.id]);

  async function adminLogin() {
    try {
      const user = await api.login(credentials.email, credentials.password);
      setStatus(`Signed in as ${user.display_name} (${user.role})`);
      setError(undefined);
    } catch (cause) { setError(String(cause)); }
  }

  async function createDraft() {
    if (!selected) return;
    try {
      const item = await api.createPolicyVersion(selected.id, {
        version: versionName, content, effective_from: effectiveFrom, effective_to: null
      });
      setDraft(item);
      setVersions(await api.policyVersions(selected.id));
      setStatus(`Draft ${item.version} created`);
    } catch (cause) { setError(String(cause)); }
  }

  async function saveDraft() {
    if (!draft) return;
    try {
      const item = await api.updatePolicyVersion(draft.id, {
        content, effective_from: effectiveFrom, effective_to: null
      });
      setDraft(item);
      setStatus(`Draft saved · ${item.content_hash.slice(0, 12)}`);
    } catch (cause) { setError(String(cause)); }
  }

  async function publish() {
    if (!draft) return;
    try {
      await api.publishPolicyVersion(draft.id);
      setVersions(await api.policyVersions(draft.policy_id));
      setDraft(undefined);
      setStatus("Policy published. Refresh the lexical index to update retrieval.");
    } catch (cause) { setError(String(cause)); }
  }

  async function rebuild() {
    setStatus("Refreshing the offline BM25 lexical index…");
    try { setStatus(JSON.stringify(await api.rebuildIndex())); }
    catch (cause) { setError(String(cause)); }
  }

  async function testQuery() {
    if (!selected) return;
    try {
      setResults(await api.testRetrieval({
        query, payer_code: selected.payer_code, plan_code: selected.plan_code,
        service_date: effectiveFrom, limit: 5
      }));
    } catch (cause) { setError(String(cause)); }
  }

  return <main className="knowledge-page">
    <section className="knowledge-header">
      <div><p className="eyebrow">VERSIONED KNOWLEDGE</p><h2>Policy and RAG administration</h2></div>
      <button onClick={() => void rebuild()}>Refresh lexical index</button>
    </section>
    {error && <div className="error-banner">{error}</div>}
    {status && <div className="status-banner">{status}</div>}
    <section className="admin-login card">
      <strong>Administrative session</strong>
      <input value={credentials.email} onChange={(e) => setCredentials({ ...credentials, email: e.target.value })} aria-label="Admin email" />
      <input type="password" value={credentials.password} placeholder="Admin password" onChange={(e) => setCredentials({ ...credentials, password: e.target.value })} aria-label="Admin password" />
      <button onClick={() => void adminLogin()}>Sign in</button>
    </section>
    <div className="knowledge-grid">
      <section className="card policy-list">
        <div className="panel-title"><h3>Policies</h3><span>{policies.length}</span></div>
        {policies.map((item) => <button key={item.id} className={selected?.id === item.id ? "selected" : ""} onClick={() => setSelected(item)}>
          <strong>{item.policy_code}</strong><small>{item.title}</small>
        </button>)}
      </section>
      <section className="card policy-editor">
        <div className="panel-title"><h3>{selected?.title ?? "Select a policy"}</h3><span>{draft ? "DRAFT" : "READ ONLY"}</span></div>
        <div className="version-strip">{versions.map((item) => <span key={item.id}>{item.version} · {item.state}</span>)}</div>
        <div className="editor-meta">
          <label>Version<input value={versionName} onChange={(e) => setVersionName(e.target.value)} disabled={Boolean(draft)}/></label>
          <label>Effective from<input type="date" value={effectiveFrom} onChange={(e) => setEffectiveFrom(e.target.value)}/></label>
        </div>
        <label>Policy source<textarea rows={16} value={content} onChange={(e) => setContent(e.target.value)}/></label>
        <div className="actions">
          {!draft && <button onClick={() => void createDraft()}>Create draft</button>}
          {draft && <><button onClick={() => void saveDraft()}>Save draft</button><button className="primary" onClick={() => void publish()}>Publish</button></>}
        </div>
      </section>
      <section className="card retrieval-test">
        <h3>Retrieval test</h3>
        <div><input value={query} onChange={(e) => setQuery(e.target.value)}/><button onClick={() => void testQuery()}>Search</button></div>
        {results.map((item) => <blockquote key={item.chunk_id}><strong>{item.policy_code} · {item.heading_path}</strong><p>{item.excerpt}</p><cite>v{item.policy_version} · score {item.score}</cite></blockquote>)}
      </section>
    </div>
  </main>;
}
