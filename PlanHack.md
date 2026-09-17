# Claim Power House — Complete Build Specification and Delivery Plan

**Document status:** implementation baseline  
**Target:** hackathon-ready, production-shaped, synthetic-data-only decision-support system  
**Products:** Version 1 VS Code desktop extension; Version 2 React web application  
**Core architecture:** shared FastAPI modular monolith, SQLite system of record, Chroma local retrieval store, bounded multi-agent workflow, human-in-the-loop decisions

---

## 1. Executive decision

Claim Power House will be a **bounded multi-agent claim-review workbench**, not a general chatbot and not an autonomous adjudicator.

Specialist agents inspect a claim, execute trusted tools, retrieve effective-dated policy evidence, and produce structured findings. A synthesis agent creates a recommendation. A human adjudicator must approve, modify, reject, pend, or route the recommendation before any final claim decision or claim-field mutation occurs.

The first release is deliberately described as a **synthetic-data decision-support demo**. It is not a production claims adjudication system and must not be used for clinical decisions, payment decisions, or real protected health information (PHI).

### Product promise

> Claim Power House helps an adjudicator resolve exception claims faster by coordinating specialist agents, deterministic checks, and cited policy evidence while preserving human control and a reproducible audit trail.

### Non-negotiable principles

1. Deterministic rules and source evidence outrank model opinion.
2. Agents have read-only access to claim data and no mutation credentials.
3. Only a server-enforced human decision endpoint may mutate a claim.
4. Every recommendation must cite versioned evidence or say that evidence is insufficient.
5. Every mutation and decision creates an audit event in the same database transaction.
6. Agent conclusions and evidence are visible; private model chain-of-thought is neither requested nor stored.
7. Synthetic data only for the hackathon and initial demo.
8. Both product versions use the same backend modules, schemas, rules, agents, MCP server, and tests.
9. Local persistence has one owner: the backend runtime. UIs never open database files directly.
10. Failures degrade safely to deterministic findings and human review.

---

## 2. Scope

### 2.1 Must be built

- Shared Python/FastAPI backend and domain layer
- Transactional SQLite application database with migrations and automatic first-run creation
- Chroma persistent retrieval store with local embeddings
- Curated synthetic test/demo dataset and repeatable seed generator
- Versioned deterministic rules engine
- Versioned policy/document ingestion, editing, approval, indexing, rollback, and deletion workflows
- Bounded multi-agent orchestration with persisted runs, steps, findings, and evidence
- Human review and atomic decision workflow
- Model Context Protocol (MCP) server exposing safe resources and tools
- Explicit internal and external tool connections with schemas and permissions
- Realtime, replayable job progress
- Version 1 installable VS Code desktop extension with a bundled local backend
- Version 2 React browser UI using the same backend and database schema
- Audit, provenance, configuration, diagnostics, backup, restore, and reset capabilities
- Unit, integration, security, retrieval, agent, UI, packaging, and end-to-end tests
- Developer scripts, CI, installation instructions, and demo runbook

### 2.2 Deferred until after the two versions are complete

- Real PHI or live payer connectivity
- Autonomous approval or denial
- Payment calculation without a deterministic pricing engine
- Multi-tenant hosting
- Horizontally scaled SQLite deployment
- Free-form executable rules edited in the UI
- Learned future-edit prediction without labeled and calibrated data
- Historical-claim outcomes as authoritative evidence
- General-purpose graph traversal unless evaluation shows measurable retrieval improvement
- Multiple LLM implementations in the first milestone
- Mobile application

---

## 3. Product versions

### 3.1 Version 1 — VS Code desktop extension

Version 1 is an offline-capable desktop product distributed as a platform-specific `.vsix` package.

#### User experience

- Activity-bar container named **Claim Power House**
- Claims queue tree view
- Claim Review webview panel
- Agent Run timeline webview
- Policy and rule editor commands
- Data import and index-management commands
- Diagnostics/output channel
- Status-bar indicator for backend health and active jobs
- Command Palette commands for initialization, health, backup, restore, reseed, and logs

#### Bundled runtime

The extension package includes:

- Compiled TypeScript extension host code
- Built React webview assets
- Platform-specific packaged Python sidecar executable
- Database migrations
- Seed manifests and curated synthetic fixtures
- Versioned rule definitions
- Starter policy corpus
- Local embedding model files or a separately checksummed offline asset installed with the VSIX release
- MCP server hosted by the Python sidecar

The release pipeline produces separate artifacts for:

- Windows x64
- macOS arm64
- macOS x64, if required
- Linux x64

The extension is desktop-only. VS Code web extensions cannot create child processes, so `vscode.dev` and browser extension hosts are explicitly unsupported for Version 1.

#### First-run behavior

1. Extension activates on the first Claim Power House command or view.
2. It creates an application directory under VS Code `globalStorageUri`.
3. It validates bundled runtime and model checksums.
4. It starts the sidecar on loopback using an OS-assigned port.
5. It passes a random per-session bearer token through the child-process environment.
6. The backend acquires a single-instance lock.
7. The backend creates or migrates the application SQLite database.
8. The backend creates or opens the Chroma persistence directory.
9. If no dataset exists, it loads the curated seed package and builds the retrieval index.
10. The extension waits for `/health/ready`, then opens the queue.

The VSIX installation directory is treated as read-only. Mutable data, logs, indexes, and configuration are written only under `globalStorageUri`.

#### Lifecycle requirements

- Start the sidecar lazily, not during every VS Code launch.
- Reuse one sidecar per VS Code profile/data directory.
- Detect and reconnect to an existing healthy sidecar.
- Terminate the owned sidecar during clean extension shutdown.
- Recover from an unclean shutdown using the process lock and job recovery rules.
- Never bind to a non-loopback interface.
- Rotate the session token on every sidecar start.
- Show actionable errors for missing CPU features, blocked executables, corrupt models, migration failures, and port failures.

#### Packaging requirements

- Package with `@vscode/vsce`.
- Generate a software bill of materials and dependency/license inventory.
- Sign executables where the target operating system supports it.
- Include SHA-256 checksums for sidecar and model assets.
- Run installation and clean-machine smoke tests for every platform artifact.
- Provide `code --install-extension <artifact>.vsix` instructions.
- Do not download executable code on first run.

### 3.2 Version 2 — React web application

Version 2 is a Vite React single-page application served by or deployed beside the same FastAPI backend.

#### User experience

- Login and session management
- Claims queue with filtering, sorting, assignment, risk, SLA age, and status
- Claim workspace with lines, findings, policy evidence, agent opinions, disagreement view, recommendation, and decision controls
- Realtime agent timeline with reconnection
- Policy/document library and RAG management
- Rule management and test runner
- Agent configuration and prompt-version viewer
- Audit timeline and controlled export
- Import history and validation errors
- System health, model health, job monitor, and index status

#### Deployment profile

- One FastAPI application instance owns the SQLite and Chroma directories.
- React is served through the FastAPI container or a colocated static server.
- Persistent application and Chroma directories are mounted as volumes.
- HTTPS is terminated by the platform ingress/load balancer.
- Secrets are supplied through environment variables or a secret manager.
- The single-node SQLite profile must not be horizontally scaled.
- A future scale-out profile replaces application SQLite with Postgres and uses a server-backed vector service/Chroma deployment plus a durable queue.

### 3.3 Shared-core rule

The extension and web application are clients of the same backend API. They must not fork business logic.

Shared components:

- Domain entities and state machines
- Database schema and migrations
- Import/normalization pipeline
- Rules engine
- RAG ingestion and query service
- Agent definitions and orchestration
- MCP resources and tools
- LLM gateway and schemas
- Audit service
- Test fixtures and golden expectations

The two products may use separate physical data directories, but their schema and behavior remain identical. If both clients need to use the same physical data, they must connect to the same running backend rather than opening the SQLite or Chroma files independently.

---

## 4. Personas and permissions

### 4.1 Roles

| Role | Capabilities |
|---|---|
| Viewer | Read claims, evidence, completed runs, and audit events |
| Adjudicator | Viewer rights plus run review, save draft, pend, request documents, accept/modify/reject recommendations, and submit decisions |
| Supervisor | Adjudicator rights plus unlock/reassign, review high-risk decisions, approve policy/rule publication, and export audits |
| Administrator | Manage users, configuration, connectors, models, backups, and system health; cannot silently alter completed decisions |

For the local hackathon profile, a seeded adjudicator and administrator may be used. Hosted environments require real password hashing and secure sessions. SSO/MFA is required before an internal pilot.

### 4.2 Primary job to be done

> As an adjudicator, I need to understand why a claim requires review, inspect the exact policy and rule evidence, see where specialist agents agree or disagree, and make a defensible decision quickly.

---

## 5. Domain state machines

Execution state must never be stored in the claim status column.

### 5.1 Claim lifecycle

```text
NEW
  -> NEEDS_REVIEW
  -> PENDED -> NEEDS_REVIEW
  -> APPROVED
  -> DENIED
  -> CANCELLED
```

Terminal claim states are `APPROVED`, `DENIED`, and `CANCELLED`. Reopening a terminal claim requires a supervisor action that creates a new claim version and audit event.

### 5.2 Adjudication job lifecycle

```text
QUEUED -> RUNNING -> WAITING_FOR_HUMAN -> COMPLETED
                   -> DEGRADED -> WAITING_FOR_HUMAN
       -> FAILED
       -> CANCELLED
```

### 5.3 Agent-step lifecycle

```text
PENDING -> RUNNING -> SUCCEEDED
                   -> SKIPPED
                   -> TIMED_OUT
                   -> FAILED
```

### 5.4 Recommendation lifecycle

```text
DRAFT -> READY -> ACCEPTED
                -> MODIFIED
                -> REJECTED
                -> EXPIRED
```

A recommendation expires when the claim, rule set, policy version, retrieval index, or allowed-action configuration changes after the recommendation snapshot.

### 5.5 Pend/document lifecycle

```text
REQUESTED -> RECEIVED -> VALIDATED -> CLAIM_RETURNED_TO_REVIEW
          -> EXPIRED
          -> CANCELLED
```

---

## 6. Multi-agent design

### 6.1 Agent roster

The MVP uses five logical agents. They run inside one orchestrated backend process; they are not separate microservices.

#### A. Intake and Validation Agent

Purpose:

- Validate schema, required fields, dates, identifiers, totals, and normalization
- Detect corrupt or incomplete imports
- Produce validation findings

Tools:

- `get_claim_snapshot`
- `validate_claim_schema`
- `calculate_claim_totals`
- `get_import_provenance`

LLM requirement: none for normal operation.

#### B. Rules Agent

Purpose:

- Execute versioned deterministic checks
- Explain failures using templated explanations
- Return rule-versioned evidence

Tools:

- `list_applicable_rules`
- `run_rule_set`
- `get_rule_definition`

LLM requirement: optional explanation only; never used to determine pass/fail.

#### C. Policy Evidence Agent

Purpose:

- Form metadata-constrained retrieval queries
- Retrieve effective-dated policy passages
- Validate applicability to payer, plan, jurisdiction, procedure, and date of service
- Return citations and retrieval scores

Tools:

- `search_policy_chunks`
- `get_policy_version`
- `get_policy_chunk`
- `check_policy_applicability`

#### D. Coding and Risk Agent

Purpose:

- Inspect diagnosis, procedure, modifier, units, authorization, duplication, and internal consistency
- Identify unusual patterns without declaring fraud
- Escalate unsupported or high-risk cases

Tools:

- `get_claim_codes`
- `lookup_code_reference`
- `check_duplicate_claim`
- `get_provider_aggregate`
- `get_member_claim_summary`

Any aggregate tool must prevent cross-member detail leakage.

#### E. Recommendation and Synthesis Agent

Purpose:

- Compare structured findings from other agents
- Apply the evidence hierarchy
- Identify agreements, conflicts, missing evidence, and uncertainty
- Propose one allowed next action and an adjudicator note

Tools:

- Read-only access to the current run's findings and evidence
- No direct claim, database, policy-edit, or decision tools

### 6.2 Orchestrator

The orchestrator is deterministic application code, not another unconstrained model.

Responsibilities:

- Create an immutable claim snapshot
- Pin rule, policy-index, prompt, model, and schema versions
- Build the execution plan
- Run independent agents in parallel where safe
- Enforce per-agent tool allowlists
- Apply time, token, result-size, and retry budgets
- Persist every state transition and tool call
- Cancel dependent steps after fatal validation failures
- Route failures to deterministic degraded mode
- Invoke synthesis only after prerequisites finish
- Enforce human review gates
- Never call the decision mutation API

### 6.3 Execution graph

```text
Create claim snapshot
        |
        v
Intake/Validation
        |
        +------------------+
        |                  |
        v                  v
Rules Agent        Coding/Risk Agent
        |                  |
        +---------+--------+
                  |
                  v
         Policy Evidence Agent
                  |
                  v
      Recommendation/Synthesis Agent
                  |
                  v
           Human review gate
                  |
                  v
 Transactional decision + audit event
```

Policy retrieval may begin concurrently using normalized claim metadata, but final applicability validation waits for deterministic inputs.

### 6.4 Evidence hierarchy

When agents disagree, synthesis uses this order:

1. Effective-dated payer/benefit policy
2. Versioned deterministic rule output
3. Claim and submitted documentation
4. Coding-reference analysis
5. De-identified aggregate/historical patterns
6. General model knowledge

Conflicting authoritative evidence always produces `NEEDS_HUMAN_REVIEW`, never an inferred resolution.

### 6.5 Agent finding schema

```json
{
  "finding_id": "fnd_01J...",
  "run_id": "run_01J...",
  "agent_type": "POLICY_EVIDENCE",
  "finding_type": "PRIOR_AUTHORIZATION_REQUIRED",
  "severity": "HIGH",
  "conclusion": "Authorization evidence is missing.",
  "confidence": 0.94,
  "reason_codes": ["AUTH_MISSING"],
  "evidence_ids": ["ev_01J..."],
  "recommended_action": "PEND_REQUEST_DOCUMENTATION",
  "limitations": [],
  "schema_version": "1.0",
  "created_at": "2026-09-16T15:00:00Z"
}
```

Confidence is an agent-reported signal, not a probability unless separately calibrated. The UI labels it accordingly.

### 6.6 Recommendation schema

```json
{
  "recommendation_id": "rec_01J...",
  "run_id": "run_01J...",
  "recommended_action": "PEND_REQUEST_DOCUMENTATION",
  "summary": "Prior authorization is required but not present.",
  "reason_codes": ["AUTH_MISSING"],
  "supporting_finding_ids": ["fnd_01J..."],
  "evidence_ids": ["ev_01J..."],
  "agent_agreement": {
    "agree": ["RULES", "POLICY_EVIDENCE", "CODING_RISK"],
    "disagree": [],
    "abstain": ["INTAKE_VALIDATION"]
  },
  "suggested_edits": [],
  "missing_evidence": ["prior_authorization_document"],
  "adjudicator_note": "Pend and request authorization documentation.",
  "requires_human_review": true,
  "limitations": [],
  "schema_version": "1.0"
}
```

Allowed recommendations:

- `APPROVE_REVIEW`
- `DENY_REVIEW`
- `PEND_REQUEST_DOCUMENTATION`
- `ROUTE_SPECIALIST`
- `CORRECT_AND_REVIEW`
- `INSUFFICIENT_EVIDENCE`

These are recommendations, not claim-state mutations.

### 6.7 Human gates

Human confirmation is mandatory when:

- Any final disposition is proposed
- A claim-field edit is proposed
- Agents disagree
- Policy evidence is missing, stale, conflicting, or inapplicable
- Confidence is below the configured threshold
- A high-dollar or high-risk threshold is reached
- An adjudicator overrides the recommendation
- Documentation is requested or marked sufficient
- A terminal claim is reopened

The decision form captures disposition, selected recommendation, accepted edits, free-text note, override reason, attestation, and the claim version displayed to the user.

---

## 7. System architecture

### 7.1 Logical architecture

```text
VS Code Extension UI             React Web UI
         |                            |
         +-------- HTTPS/loopback API-+
                       |
              FastAPI modular monolith
                       |
   +---------+---------+----------+----------+
   |         |         |          |          |
 Claims   Workflow   Agents     RAG/MCP    Audit
   |         |         |          |          |
   +---------+---------+----------+----------+
                       |
       +---------------+----------------+
       |                                |
Application SQLite             Chroma persistence
(system of record)       (SQLite metadata + vector index files)
```

### 7.2 Technology baseline

| Layer | Choice |
|---|---|
| Extension host | TypeScript, VS Code Extension API |
| Extension UI | React webview, bundled static assets |
| Web UI | React + TypeScript + Vite |
| Server state | TanStack Query or equivalent |
| Forms/schema | React Hook Form plus generated JSON-schema types or equivalent |
| Backend | Python, FastAPI, Pydantic, SQLAlchemy 2.x, Alembic |
| Application DB | SQLite in WAL mode |
| Retrieval | Chroma `PersistentClient` for local/single-node profile |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` initial baseline |
| Lexical search | SQLite FTS5 |
| Realtime | Server-Sent Events with persisted event IDs |
| Agent orchestration | Explicit persisted state machine in application code |
| MCP | Official Python SDK; stdio locally, Streamable HTTP for hosted profile |
| Tests | Pytest, Vitest, React Testing Library, Playwright, VS Code test harness |
| Packaging | Docker for web; `vsce` plus packaged sidecar for extension |

All dependency versions must be pinned in lockfiles at implementation time. Automated dependency updates require tests and human review.

### 7.3 Repository structure

```text
claim-power-house/
  apps/
    api/
      app/
        main.py
        config.py
        auth/
        claims/
        workflow/
        agents/
        rules/
        rag/
        mcp_server/
        llm/
        audit/
        imports/
        admin/
        observability/
      migrations/
      tests/
    web/
      src/
      tests/
    vscode-extension/
      src/
      webview-ui/
      resources/
      tests/
  packages/
    api-contract/
    ui-components/
    test-fixtures/
  data/
    seed/
    policies/
    code-reference/
    golden/
  models/
    manifest.json
  scripts/
    bootstrap/
    seed/
    package-extension/
    backup/
    restore/
    smoke/
  deploy/
    docker/
    local/
  docs/
    architecture/
    threat-model/
    runbooks/
    decisions/
  .github/workflows/
  Makefile
  README.md
```

---

## 8. Persistence design

### 8.1 Two-store model

There are two persistent stores, each with a different responsibility:

1. `claim_powerhouse.db`: transactional system of record for claims, users, workflow, agents, citations, configuration metadata, and audit events.
2. `chroma/`: Chroma persistence directory containing vector collections, metadata storage, and vector index files.

Chroma is not the claim database. Chroma data is always rebuildable from approved source documents and the application database. The application database is authoritative.

Suggested directory layout:

```text
data-root/
  db/claim_powerhouse.db
  chroma/chroma.sqlite3
  chroma/<collection-index-files>
  documents/<content-addressed-files>
  models/<embedding-model-files>
  backups/
  logs/
  instance.lock
```

### 8.2 SQLite startup settings

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
PRAGMA synchronous = NORMAL;
```

Requirements:

- One backend process owns write access.
- All money is stored as integer minor units plus ISO 4217 currency code, or as fixed-precision decimal text; never binary floating point.
- All timestamps are UTC ISO-8601 at API boundaries and UTC-aware values internally.
- Every mutable aggregate has an integer `version` for optimistic concurrency.
- IDs are UUIDv7/ULID-style sortable opaque identifiers.
- JSON columns are schema-validated before persistence.
- Migrations are forward-only in release artifacts and backed up before execution.
- Startup migration failure prevents readiness.

### 8.3 Core relational tables

#### Identity and access

- `users`: identity, display name, email, password hash/SSO subject, status, version, timestamps
- `roles`: role code and description
- `user_roles`: user/role relation
- `sessions`: hashed token ID, user, expiry, revocation, client metadata
- `permissions`: optional fine-grained permission catalog
- `role_permissions`: role permission mapping

#### Claim domain

- `members`: synthetic member identity and demographic attributes
- `providers`: synthetic provider attributes and identifiers
- `payers`: simulated payer metadata
- `plans`: payer plan, jurisdiction, effective dates
- `claims`: external ID, member, provider, payer/plan, type, status, version, currency, billed/allowed/paid minor units, dates, assignment, risk, timestamps
- `claim_lines`: claim, line number, procedure, modifiers, units, amounts, status, denial reason
- `claim_diagnoses`: claim, optional line, diagnosis system/code, sequence, present-on-admission flag
- `claim_documents`: claim/document relationship and document purpose
- `authorizations`: member/provider/procedure scope, authorization identifier, validity, units
- `claim_snapshots`: immutable canonical JSON and hash used by a run
- `claim_decisions`: disposition, deciding user, recommendation reference, attestation, override reason, claim version, timestamps
- `document_requests`: requested type, due date, state, received document, resolution

#### Rules and policy

- `rules`: stable rule code, name, category, severity, implementation key, active flag
- `rule_versions`: rule, semantic version, parameters JSON, explanation template, effective dates, approval state, hash
- `rule_sets`: named set and version
- `rule_set_members`: rule set/version mapping and priority
- `rule_results`: run, claim snapshot, rule version, passed, evidence JSON, duration
- `policy_documents`: stable policy identity, payer/plan, title, source, jurisdiction
- `policy_versions`: document, version, effective dates, approval state, content hash, superseded version
- `policy_chunks`: policy version, ordinal, heading path, text, token count, content hash, Chroma ID
- `policy_code_scopes`: policy version mapped to diagnosis/procedure/modifier/service categories
- `rag_index_versions`: embedding model/version, chunking version, collection name, source-set hash, status
- `rag_index_members`: index version, policy chunk, embedding status, error

#### Multi-agent workflow

- `adjudication_jobs`: claim, claim version, status, idempotency key, correlation ID, requested by, timestamps, failure
- `agent_runs`: job, agent type, prompt version, model config, state, budgets, timings
- `agent_steps`: run, step/tool, status, input/output hashes, timings, error
- `agent_findings`: structured finding fields and schema version
- `evidence_items`: type, source IDs, exact excerpt, source hash, applicability, retrieval metrics
- `finding_evidence`: finding/evidence relation
- `recommendations`: structured recommendation, status, schema version, expiry reason
- `recommendation_findings`: recommendation/finding relation
- `suggested_edits`: recommendation, JSON Pointer field path, before/after values, reason, allowed flag
- `job_events`: monotonic sequence, job, event type, public payload, timestamp
- `tool_invocations`: agent run, tool, validated arguments/result, approval state, latency, error

#### Models, prompts, and connections

- `llm_providers`: provider code and non-secret configuration reference
- `model_configs`: provider, model ID, temperature, limits, active state
- `prompt_templates`: agent type and stable prompt name
- `prompt_versions`: template, version, content hash, schema version, approval state
- `llm_calls`: agent run, provider/model, prompt version, redacted request/response or hashes, token usage, latency, status
- `tool_definitions`: name, version, input/output schemas, risk class, active state
- `agent_tool_permissions`: agent type/tool/version mapping
- `connections`: connector type, display name, state, non-secret settings, secret reference
- `connection_health`: connection, check time, latency, result/error

#### Imports and audit

- `import_batches`: source type, file hash, manifest, status, counts, requester
- `import_errors`: batch, record locator, code, safe message, details
- `audit_events`: sequence, actor, actor type, session, claim, correlation ID, event type, canonical before/after/details, previous hash, event hash, timestamp
- `exports`: requester, filter, artifact hash, expiry, status
- `schema_migrations`: managed by Alembic

### 8.4 Audit integrity

“Append-only” is enforced, not merely documented:

- Application repositories expose insert/read operations only for audit events.
- SQLite triggers reject update and delete against `audit_events` in normal operation.
- The database user/process still has physical control in the local edition, so local audit is tamper-evident rather than independently immutable.
- Each event includes `previous_hash` and `event_hash` over canonical fields to detect alteration or deletion.
- Backup/export verification checks the hash chain.
- Production evolution sends signed audit events to externally controlled append-only storage.

### 8.5 Backup and restore

- Use SQLite online backup API or safe backup command, not raw copying during writes.
- Quiesce Chroma ingestion, then snapshot its persistence directory.
- Include a manifest with schema version, index version, file hashes, app version, and creation time.
- Restore into a new directory, validate hashes, run migration validation, and only then switch the active directory.
- Chroma can be rebuilt from approved documents if its backup is unavailable.

---

## 9. Test and demonstration data

### 9.1 Data strategy

The default installation uses a curated, deterministic synthetic dataset. External public synthetic datasets are optional import demonstrations, not required for the core demo.

Seed package:

- 30 synthetic members
- 12 synthetic providers
- 1 simulated payer
- 2 simulated plans
- 20–30 claims
- 40–80 claim lines
- 8–12 policy documents with effective-dated versions
- 5 initial deterministic rules
- 10–15 golden adjudication scenarios
- Seed users for local mode only

All people, providers, identifiers, addresses, and documents are explicitly synthetic. Add a scanner that rejects known real-data patterns and secrets before packaging.

### 9.2 Golden scenarios

At minimum:

1. Clean claim with no exception
2. Missing diagnosis
3. Invalid procedure/modifier combination
4. Units above policy limit
5. Missing prior authorization
6. Expired prior authorization
7. Duplicate claim
8. Missing supporting documentation
9. High-dollar supervisor review
10. Frequency limit exceeded
11. Policy exclusion
12. Policy version changes across dates of service
13. Conflicting policy evidence
14. Malicious instruction embedded in a policy document
15. LLM unavailable or malformed output

Each golden case includes:

- Input claim and related records
- Expected validation results
- Expected deterministic findings
- Expected applicable policy versions and chunk IDs
- Permitted recommendations
- Mandatory human gate reason
- Expected audit events
- Maximum execution time budget

LLM prose is not compared verbatim. Tests validate schema, allowed actions, citations, grounding, and invariant behavior.

### 9.3 Optional import adapters

Implement adapters in this order:

1. Native Claim Power House JSON fixture format
2. CSV demo format with manifest
3. FHIR ExplanationOfBenefit subset
4. CMS synthetic/SynPUF mapping
5. Synthea-derived fixtures

Every adapter maps into one canonical claim model and produces row-level validation errors. Raw imports are content-addressed and linked to import provenance.

### 9.4 Seed repeatability

- A fixed random seed produces stable identifiers and values.
- `seed_version` is stored in the database.
- Reseeding requires explicit confirmation and creates a backup first.
- CI generates the seed twice and verifies identical canonical hashes.

---

## 10. Deterministic rules engine

### 10.1 Initial rules

- `REQ_FIELD_001`: required claim or line field missing
- `UNIT_LIMIT_001`: submitted units exceed effective policy maximum
- `AUTH_001`: required authorization absent or invalid
- `CODE_PAIR_001`: procedure/modifier/diagnosis relationship invalid
- `DUP_CLAIM_001`: duplicate or near-duplicate claim detected

### 10.2 Rule interface

```python
class ClaimRule(Protocol):
    key: str
    version: str

    def applies(self, snapshot: ClaimSnapshot, context: RuleContext) -> bool: ...
    def evaluate(self, snapshot: ClaimSnapshot, context: RuleContext) -> RuleResult: ...
```

Rules are registered code selected by `implementation_key`. Database records contain approved parameters, descriptions, and effective dates—not arbitrary Python.

### 10.3 Rule publication

```text
DRAFT -> TESTED -> APPROVED -> ACTIVE -> RETIRED
```

Activation requires:

- Schema validation
- Unit tests
- Execution against all golden cases
- Diff report against the active version
- Supervisor approval
- Effective date
- Rollback target

---

## 11. RAG and editable knowledge base

### 11.1 Recommendation on Chroma and MiniLM

Use Chroma `PersistentClient` for the local extension and the single-node demo. Chroma's current local persistence uses SQLite for metadata and separate vector index files. It is suitable for this local/demo profile; it should not be presented as the enterprise production storage architecture.

Use `sentence-transformers/all-MiniLM-L6-v2` as the initial offline embedding baseline because it is compact, CPU-friendly, widely supported, and produces 384-dimensional vectors. It is designed for sentences and short paragraphs and truncates longer inputs, so retrieval must use short semantic chunks.

Recommended initial chunking:

- Heading-aware policy sections
- Target 180–220 tokenizer tokens
- 30–40 token overlap
- Never cross a policy-version or major-section boundary
- Preserve heading path and exact source offsets
- Store the unmodified source excerpt for citation

MiniLM is not assumed to understand every medical-policy distinction. Therefore the required retrieval approach is hybrid:

1. Exact metadata constraints
2. Code/keyword and SQLite FTS5 matching
3. Chroma semantic similarity
4. Reciprocal-rank or weighted fusion
5. Deterministic applicability filtering
6. Optional reranking only after evaluation

Before changing embedding models, run the labeled retrieval evaluation. Model name, model revision/hash, vector dimension, normalization method, and chunking version are part of the index version. Changing any of them requires a new collection and full reindex.

### 11.2 Chroma collections

- `policy_chunks_<index_version>`
- `code_reference_<index_version>`
- `approved_guidance_<index_version>`

Do not mix draft and approved policy chunks. Do not use raw historical claim narratives in the initial vector store.

Required Chroma metadata:

```json
{
  "chunk_id": "pch_01J...",
  "policy_id": "POL-104",
  "policy_version_id": "polv_01J...",
  "payer_id": "payer_demo",
  "plan_id": "plan_gold",
  "jurisdiction": "DEMO",
  "effective_from": "2026-01-01",
  "effective_to": null,
  "approval_state": "APPROVED",
  "heading_path": "Coverage > Authorization",
  "content_hash": "sha256:...",
  "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
  "index_version": "rag-1"
}
```

### 11.3 Ingestion pipeline

```text
Upload/import
 -> virus/type/size validation
 -> text extraction
 -> source normalization
 -> draft policy version
 -> human review
 -> approval/effective dating
 -> heading-aware chunking
 -> chunk/hash persistence
 -> embedding generation
 -> write new Chroma collection
 -> retrieval evaluation
 -> atomic index activation
```

The active index pointer changes only after all required chunks are embedded and validation passes.

### 11.4 Policy/RAG editing workflow

The UI never edits an indexed chunk in place.

1. User opens an approved policy version.
2. User creates a new draft version.
3. User edits source content and metadata.
4. System displays a semantic and textual diff.
5. User runs impacted golden tests and retrieval evaluation.
6. Supervisor approves the version and effective dates.
7. System creates new chunks and a new index version.
8. System activates the new index atomically.
9. Previous versions remain available for claims with earlier dates of service.

Supported operations:

- Create draft
- Edit metadata/content
- Preview chunks
- Test retrieval with a sample query/claim
- Compare retrieval before and after
- Approve and publish
- Schedule future activation
- Retire without erasing history
- Roll back active index pointer
- Rebuild an index
- Remove an incorrectly ingested draft
- Record legal deletion/tombstone while preserving required audit metadata

### 11.5 Query pipeline

1. Derive payer, plan, jurisdiction, date of service, claim type, and codes from the immutable claim snapshot.
2. Reject missing mandatory scope instead of searching globally.
3. Filter to approved policy versions effective on the date of service.
4. Execute FTS/code search and Chroma similarity search.
5. Fuse and deduplicate results.
6. Validate applicability.
7. Return top evidence within a fixed token budget.
8. Persist query, filters, index version, candidate IDs, scores, selected IDs, and rejection reasons.

### 11.6 Retrieval evaluation

Metrics:

- Recall@k for expected policy chunks
- Precision@k
- Mean reciprocal rank
- Effective-date accuracy
- Payer/plan filter accuracy
- Citation correctness
- Unsupported-answer rate
- Retrieval latency

Initial gate:

- 100% effective-date and payer/plan correctness on golden cases
- Recall@5 at least 0.90 on labeled demo queries
- No draft/retired policy leakage
- No malicious embedded instruction changes agent/tool behavior

---

## 12. MCP server

### 12.1 Purpose

The MCP server provides a typed boundary between agents and application capabilities. It also enables approved external MCP-capable hosts to inspect synthetic claim resources and invoke safe tools.

MCP is not a bypass around application authorization. Every MCP request is authenticated, authorized, correlated, schema-validated, rate-limited, and audited.

### 12.2 Transports

- Version 1: local `stdio` MCP transport started by the extension/sidecar.
- Version 2 local/single-node: authenticated Streamable HTTP endpoint under `/mcp`.
- Remote deployment: HTTPS Streamable HTTP with OAuth-compliant audience-bound tokens and least-privilege scopes.

### 12.3 MCP resources

Resource URI patterns:

- `claim://claims/{claim_id}` — redacted claim summary
- `claim://claims/{claim_id}/lines` — claim lines
- `claim://claims/{claim_id}/audit` — authorized audit timeline
- `claim://runs/{run_id}` — run summary and statuses
- `claim://runs/{run_id}/findings` — agent findings
- `policy://documents/{policy_id}/versions/{version_id}` — approved policy version
- `policy://chunks/{chunk_id}` — exact cited chunk
- `rule://rules/{rule_code}/versions/{version}` — rule definition
- `system://health` — safe health/readiness summary

Resources expose only data allowed by the caller's role and claim scope.

### 12.4 MCP tools

#### Read-only tools, model-callable

- `get_claim_snapshot`
- `get_claim_codes`
- `get_import_provenance`
- `list_applicable_rules`
- `run_rule_set`
- `get_rule_definition`
- `search_policy_chunks`
- `get_policy_chunk`
- `check_policy_applicability`
- `lookup_code_reference`
- `check_duplicate_claim`
- `get_provider_aggregate`
- `get_member_claim_summary`
- `get_agent_findings`
- `get_run_status`

#### Proposal tools, model-callable but non-mutating

- `propose_recommendation`
- `propose_claim_edit`
- `draft_adjudicator_note`
- `propose_document_request`
- `flag_conflicting_evidence`

These create run-scoped proposals only. They cannot modify a claim or recommendation status.

#### Human-confirmed tools, UI-callable only

- `start_adjudication`
- `cancel_adjudication`
- `submit_claim_decision`
- `submit_recommendation_override`
- `create_document_request`
- `publish_policy_version`
- `activate_rule_version`
- `activate_rag_index`
- `restore_backup`
- `reset_demo_data`

These are not included in agent tool allowlists. The UI displays impact and obtains explicit confirmation.

### 12.5 MCP prompts

- `review_claim_exception`
- `explain_rule_findings`
- `find_policy_support`
- `compare_agent_findings`
- `draft_human_review_note`

Prompts are convenience templates, versioned and treated as application artifacts.

### 12.6 Tool safety

- JSON Schema input and output validation
- Maximum payload/result sizes
- Strict timeouts and cancellation
- Role and claim-scope authorization before execution
- Tool-specific rate limits
- No SQL, filesystem path, URL, or code execution arguments from a model
- Content returned from imports/retrieval is labeled untrusted
- Tool descriptions and annotations from external MCP servers are treated as untrusted
- External MCP connections are disabled by default
- Every call records caller, tool version, safe arguments/result or hashes, timing, approval, and error

---

## 13. Tool and connector architecture

### 13.1 Internal tool connections

| Connection | Owner | Access |
|---|---|---|
| Application database | Repository layer | Transactional read/write; agents use service tools only |
| Chroma | RAG service | Read during runs; controlled writes during indexing |
| SQLite FTS5 | RAG service | Read during retrieval; controlled writes during publication |
| Rules engine | Rules service | Deterministic execution |
| Embedding runtime | Index/query service | Local inference only |
| LLM provider | LLM gateway | Structured recommendation/explanation only |
| MCP server | Tool gateway | Typed resources/tools with authorization |
| File import | Import service | Sandboxed file parsing and validation |
| SSE stream | Realtime service | Authorized, redacted, persisted events |

### 13.2 Initial external connections

Only one LLM provider adapter must be implemented initially. The provider is selected through server configuration, not by an agent.

Connection contract includes:

- Provider/model ID
- Data-retention and training-use configuration acknowledgement
- Endpoint/base URL allowlist
- Timeout, retry, concurrency, and token limits
- Structured-output support
- Health check
- Secret reference, never plaintext database storage
- Redaction policy
- Circuit breaker
- Cost/usage accounting

Optional dataset downloaders and FHIR endpoints are development/import tools, not runtime dependencies.

### 13.3 Future connectors

- FHIR server
- Payer policy repository
- Document management system
- Enterprise identity provider
- Durable audit sink
- Postgres
- Server-backed Chroma/vector store
- Notification service

Every future connector must implement the same connection registry, health check, least-privilege scopes, timeout policy, and audit hooks.

---

## 14. API contract

All mutation endpoints require authentication, authorization, correlation ID, idempotency key where applicable, and expected aggregate version.

### 14.1 System and auth

```text
GET  /health/live
GET  /health/ready
GET  /api/v1/system/info
POST /api/v1/auth/login
POST /api/v1/auth/logout
GET  /api/v1/me
```

### 14.2 Claims

```text
GET  /api/v1/claims
POST /api/v1/claims/import
GET  /api/v1/claims/{claim_id}
PUT  /api/v1/claims/{claim_id}/draft
POST /api/v1/claims/{claim_id}/assign
POST /api/v1/claims/{claim_id}/decisions
GET  /api/v1/claims/{claim_id}/audit
POST /api/v1/claims/{claim_id}/document-requests
POST /api/v1/document-requests/{request_id}/receive
```

### 14.3 Adjudication and agents

```text
POST /api/v1/claims/{claim_id}/adjudications
GET  /api/v1/adjudications/{job_id}
POST /api/v1/adjudications/{job_id}/cancel
GET  /api/v1/adjudications/{job_id}/events
GET  /api/v1/adjudications/{job_id}/findings
GET  /api/v1/adjudications/{job_id}/recommendation
POST /api/v1/adjudications/{job_id}/recommendation-response
```

The events endpoint supports `Last-Event-ID` and replays persisted events after the supplied sequence.

### 14.4 Rules

```text
GET  /api/v1/rules
GET  /api/v1/rules/{rule_id}
POST /api/v1/rules/{rule_id}/versions
POST /api/v1/rules/test
POST /api/v1/rule-versions/{version_id}/approve
POST /api/v1/rule-versions/{version_id}/activate
POST /api/v1/rule-versions/{version_id}/retire
```

### 14.5 Policies and RAG

```text
GET  /api/v1/policies
POST /api/v1/policies/import
GET  /api/v1/policies/{policy_id}
POST /api/v1/policies/{policy_id}/versions
PUT  /api/v1/policy-versions/{version_id}
GET  /api/v1/policy-versions/{version_id}/diff
POST /api/v1/policy-versions/{version_id}/preview-chunks
POST /api/v1/policy-versions/{version_id}/approve
POST /api/v1/rag/indexes
GET  /api/v1/rag/indexes/{index_id}
POST /api/v1/rag/indexes/{index_id}/evaluate
POST /api/v1/rag/indexes/{index_id}/activate
POST /api/v1/rag/query-test
```

### 14.6 Administration

```text
GET  /api/v1/admin/jobs
GET  /api/v1/admin/connections
POST /api/v1/admin/connections/{connection_id}/test
GET  /api/v1/admin/models
GET  /api/v1/admin/prompts
GET  /api/v1/admin/audit/export
POST /api/v1/admin/backups
POST /api/v1/admin/restores
POST /api/v1/admin/demo/reset
```

Internal raw `/llm/recommend` and unrestricted `/rag/query` endpoints are not exposed as public product APIs.

---

## 15. User-interface specification

### 15.1 Claims queue

- Status, assignment, risk, suggested action, SLA age, payer, provider, billed amount
- Search, filters, sorting, pagination
- Visible stale/reprocessing indicators
- Keyboard navigation and accessible labels
- Empty, loading, partial, error, and offline states

### 15.2 Claim workspace

- Claim summary and version
- Member/provider summary
- Lines, diagnoses, procedures, modifiers, units, and financials
- Validation and rule findings
- Policy evidence with source, version, effective dates, and exact cited text
- Agent cards with status, conclusion, evidence, limitations, and confidence label
- Agreement/disagreement matrix
- Synthesized recommendation
- Proposed field edits as before/after diff
- Missing-document checklist
- Human decision panel
- Audit timeline

### 15.3 Human decision panel

- Approve, deny, pend/request documents, route, or return for correction
- Recommendation response: accept, modify, or reject
- Required reason when overriding
- Required acknowledgement of evidence reviewed
- Expected claim version displayed and submitted
- Confirmation screen showing exact state/field changes
- Server response and audit-event ID after commit

### 15.4 Realtime trace

Display safe operational summaries, not hidden model reasoning:

- Claim snapshot created
- Validation completed
- Rules executed
- Policy search completed
- Coding/risk checks completed
- Specialist findings ready
- Synthesis completed
- Human review required
- Decision committed

Each event includes timestamp, state, duration when complete, and a link to structured output where authorized.

### 15.5 RAG administration

- Policy list and version states
- Source editor/import
- Metadata and effective dates
- Source diff
- Chunk preview
- Test query console
- Before/after retrieval comparison
- Index build progress
- Evaluation report
- Publish/rollback controls
- Source-to-citation trace

### 15.6 Accessibility

- WCAG-oriented color contrast
- Full keyboard operation for primary flow
- ARIA labels and status announcements
- No meaning conveyed only through color
- VS Code high-contrast theme testing
- Reduced-motion support for live timeline

---

## 16. Security, privacy, and safety

### 16.1 Data boundary

- Synthetic data only in demo builds.
- Startup banner and UI watermark state: **Synthetic demo — not for clinical or payment use**.
- External model transmission is deny-by-default until a provider is explicitly configured.
- Prompt, response, trace, log, screenshot, export, and backup data are included in the data-classification policy.

### 16.2 Application controls

- Backend-enforced RBAC on every route, resource, event stream, and MCP capability
- Secure password hashing for hosted local accounts
- Secure, HTTP-only, SameSite cookies for the web UI
- CSRF protection for cookie-authenticated mutations
- Session expiry, revocation, lockout, and rate limiting
- Loopback bearer token for the extension sidecar
- CORS allowlist; no wildcard in hosted mode
- Content Security Policy for React and VS Code webviews
- File size/type limits and archive-bomb protection
- Secrets in OS keychain/secret manager or environment references
- No secrets in SQLite, logs, VSIX, source fixtures, or frontend bundles

### 16.3 Agent and prompt safety

- Retrieved documents, claim notes, imported text, and external MCP descriptions are untrusted input.
- System instructions explicitly separate data from commands.
- Agents use fixed allowlists and structured schemas.
- Tool arguments are produced and validated independently of free-form prose.
- Models cannot construct SQL, filesystem paths, arbitrary URLs, or executable code.
- Model output never becomes a database update without deterministic validation and human confirmation.
- Prompt injection cases are part of every release test.
- Raw private chain-of-thought is not requested, exposed, or logged.

### 16.4 Before real PHI or an internal pilot

Require formal security, privacy, legal/compliance, and claims-operations approval; threat modeling; SSO/MFA; encryption/key management; retention/deletion policy; incident response; vendor/data-processing review; appropriate healthcare agreements; penetration testing; and compliant adverse-decision/appeal workflows.

---

## 17. Reliability and observability

### 17.1 Job reliability

- Persist job before scheduling work.
- Use compare-and-set state transitions.
- Recover `RUNNING` jobs with expired leases at startup.
- Bound concurrency to protect SQLite and local CPU.
- Retry transient provider calls only; never retry decisions blindly.
- Use idempotency keys for job creation and decision submission.
- Reject stale decisions through `expected_claim_version`.
- Persist SSE event before publishing it.

### 17.2 Metrics

- API and tool latency/error rate
- Queue depth and job duration
- Per-agent duration and failure rate
- Rule trigger distribution
- Retrieval recall/latency and zero-result rate
- LLM latency, token usage, schema failure, timeout, and cost
- Recommendation acceptance, modification, override, and abstention rates
- Human review duration
- Audit-chain verification status
- Database size, WAL size, backup age, and index health

### 17.3 Logging

- Structured JSON logs with correlation ID
- Redaction before emission
- No full claim payloads, credentials, raw prompts, or policy documents by default
- Configurable retention and rotation
- User-visible diagnostics bundle with sensitive fields removed

---

## 18. Testing strategy

### 18.1 Backend unit tests

- State transitions
- Money/date handling
- Canonicalization and hashing
- Rule applicability/evaluation
- Policy effective dating
- Retrieval fusion and filtering
- Schema validation
- Permission decisions
- Audit hash chain
- Redaction

### 18.2 Integration tests

- Fresh database creation and every migration path
- Transactional decision plus audit insertion
- Concurrent update rejection
- Duplicate idempotency request behavior
- Job lease and restart recovery
- SSE replay/reconnection
- Chroma index creation, activation, rollback, and rebuild
- Embedding/model mismatch detection
- Backup and restore
- MCP resource and tool schemas
- LLM provider timeout, retry, circuit breaker, and malformed response

### 18.3 Agent evaluations

- Correct tool selection
- Tool allowlist enforcement
- Evidence citation validity
- Effective-date correctness
- Agreement/disagreement reporting
- Unsupported-answer abstention
- Prompt-injection resistance
- No mutation-capable call path
- Stable allowed action under prose variation

### 18.4 Security tests

- RBAC denial on every endpoint and MCP resource/tool
- Cross-claim and cross-member leakage attempts
- SQL/path/URL injection
- CSRF and CORS behavior
- Session expiry/revocation
- SSE authorization and event leakage
- Malicious document/policy instructions
- Secret and real-identifier scanner over fixtures, logs, bundles, screenshots, and exports
- Dependency and container scanning

### 18.5 UI tests

- Queue and filters
- Claim detail rendering
- Run initiation and duplicate-click handling
- Live timeline and reconnect
- Evidence navigation
- Agent disagreement presentation
- Accept/modify/reject recommendation
- Stale claim conflict
- Pend/request/resume
- Audit display
- RAG edit, preview, evaluation, publish, and rollback
- Keyboard and accessibility checks

### 18.6 Packaging tests

- Install each VSIX on a clean supported OS image
- First-run DB/index creation without internet
- Upgrade while preserving data
- Uninstall/reinstall data behavior
- Sidecar startup/shutdown and crash recovery
- Paths containing spaces and non-ASCII characters
- Read-only extension installation directory
- Docker first start, migration, persistence, restart, backup, and restore

### 18.7 Performance targets for demo hardware

- Queue first render: under 2 seconds after backend readiness
- Deterministic rules: under 1 second per demo claim
- Retrieval: under 2 seconds per query on warm local index
- 90% of complete review jobs: under 10 seconds when provider responds normally
- Rules-only degraded result: under 4 seconds
- SSE reconnect and replay: under 2 seconds

---

## 19. Delivery plan

Each phase ends with a demonstrable acceptance gate. Later phases do not compensate for a failed earlier gate.

### Phase 0 — Product and architecture freeze

Deliverables:

- Intended-use statement and non-goals
- Claim, job, step, recommendation, and document-request state diagrams
- Canonical schemas and API contracts
- Threat model and data-flow diagram
- Golden-case specification
- Architecture decision records for SQLite, Chroma, MiniLM, MCP, SSE, and packaging

Gate: team can walk through every state transition, mutation owner, and human gate without ambiguity.

### Phase 1 — Monorepo and local foundation

Deliverables:

- Repository structure and lockfiles
- FastAPI shell and configuration
- React shell
- VS Code extension shell
- Health/readiness endpoints
- CI for lint, type check, unit tests, and builds
- Local developer bootstrap

Gate: clean checkout starts development services and runs tests with one documented command.

### Phase 2 — Database and synthetic data

Deliverables:

- Full initial SQLite schema and Alembic migrations
- Automatic first-run database creation
- Repository layer and transaction boundaries
- Seed generator, curated policies, claims, and golden expectations
- Import validation/reporting
- Backup/restore baseline

Gate: create, migrate, seed, backup, destroy test instance, restore, and verify canonical hashes.

### Phase 3 — Claims, auth, and audit

Deliverables:

- Login/session/RBAC profiles
- Queue and claim detail APIs
- Claim versioning and assignment
- Decision endpoint with idempotency/concurrency control
- Append-only tamper-evident audit chain
- Minimal queue and workspace UI

Gate: manual human decision works without AI; every mutation and decision is atomically audited.

### Phase 4 — Rules engine

Deliverables:

- Rule registry and five versioned rules
- Rule-set/version publication workflow
- Rule execution persistence
- Golden-case rule tests
- Rule test UI

Gate: every golden claim produces its exact expected deterministic findings.

### Phase 5 — RAG and policy editing

Deliverables:

- Policy source/version/chunk model
- Chroma local persistence and MiniLM embedding service
- SQLite FTS5 plus semantic hybrid search
- Effective-date and payer/plan filters
- Draft/edit/diff/preview/approve/publish/rollback workflow
- Retrieval test console and evaluation suite

Gate: retrieval metrics and leakage/injection gates in Section 11.6 pass.

### Phase 6 — Persisted jobs and realtime

Deliverables:

- Job/step/event state machines
- Bounded in-process worker and leases
- Restart recovery and cancellation
- Authorized SSE with replay
- Realtime timeline UI

Gate: forced backend termination during every job stage recovers safely without duplicate jobs, decisions, or events.

### Phase 7 — MCP and tool gateway

Deliverables:

- MCP stdio and Streamable HTTP profiles
- Resource and tool catalog
- Input/output schema validation
- Role/agent allowlists
- Consent/confirmation integration for human tools
- Tool audit and test suite

Gate: automated negative tests prove agents cannot discover or invoke mutation tools.

### Phase 8 — Multi-agent workflow

Deliverables:

- Five agent definitions
- Deterministic orchestrator
- Per-agent prompts, models, budgets, and tool permissions
- Finding/evidence schemas
- Parallel execution where safe
- Conflict detection and degraded mode

Gate: all golden cases produce valid findings; injected instructions cannot alter tools, permissions, or state.

### Phase 9 — Recommendation and human review

Deliverables:

- One LLM provider implementation
- Structured synthesis output
- Evidence hierarchy and abstention
- Recommendation/diff UI
- Accept/modify/reject and override-reason flow
- Atomic final decision

Gate: no model-controlled path mutates a claim; all recommendations are schema-valid, cited, and human-gated.

### Phase 10 — VS Code extension release

Deliverables:

- Finished views, commands, webviews, diagnostics, and lifecycle
- Platform-specific bundled sidecars
- Offline model and seed assets
- First-run self-building stores
- Upgrade/migration logic
- VSIX packages, checksums, install guide, and clean-machine tests

Gate: a user installs the VSIX on a clean supported computer, stays offline, opens the seeded queue, completes a golden review, restarts VS Code, and sees preserved data/audit history.

### Phase 11 — React web release

Deliverables:

- Complete queue/workspace/admin/RAG/audit UI
- Secure hosted-session profile
- Docker packaging and persistent volumes
- Deployment, backup, restore, and upgrade runbooks
- Browser end-to-end suite

Gate: a new single-node deployment completes all golden scenarios, survives restart, and restores from backup.

### Phase 12 — Hardening and demo certification

Deliverables:

- Accessibility and performance review
- Security scans and threat-model verification
- Failure-mode exercises
- Dependency/SBOM/license review
- Demo replay/canned provider fallback, visibly labeled
- Operator and presenter runbooks
- Release artifacts and signed manifests

Gate: all Definition of Done items pass in a release-candidate environment.

---

## 20. Definition of Done

### 20.1 Shared platform

- [ ] Fresh stores initialize and migrate automatically.
- [ ] Synthetic seed package loads repeatably.
- [ ] All golden deterministic results pass.
- [ ] Retrieval gates pass with exact, effective-dated citations.
- [ ] Agent outputs validate against versioned schemas.
- [ ] Agents cannot access mutation tools.
- [ ] Conflicts and insufficient evidence route to human review.
- [ ] Every mutation and decision is atomically audited.
- [ ] Idempotency and optimistic concurrency tests pass.
- [ ] SSE reconnects and replays without data loss or duplication.
- [ ] LLM failure produces a usable deterministic review.
- [ ] Backup, restore, and Chroma rebuild are demonstrated.
- [ ] No real identifiers, PHI, or secrets exist in release artifacts.

### 20.2 Version 1

- [ ] Platform VSIX installs on a clean machine.
- [ ] No Python, database, model, or project setup is required from the user.
- [ ] First run builds both persistent stores and seeds demo data.
- [ ] The extension operates offline except for an optionally configured LLM provider.
- [ ] Local sidecar is loopback-only and session-authenticated.
- [ ] Upgrade preserves and migrates data.
- [ ] Full hero workflow completes inside VS Code.

### 20.3 Version 2

- [ ] React application implements the same workflows and contracts.
- [ ] Hosted authentication, sessions, CSRF, CORS, and RBAC tests pass.
- [ ] Docker deployment persists both stores across restart.
- [ ] Single-writer deployment constraint is documented and enforced operationally.
- [ ] Admin RAG workflow and audit viewer are complete.
- [ ] Browser end-to-end suite passes.

### 20.4 Demo success

- [ ] A first-time reviewer resolves each of three hero claims in under 60 seconds.
- [ ] At least 90% of demo reviews finish within 10 seconds under normal provider conditions.
- [ ] Every recommendation contains valid evidence or explicitly declares insufficient evidence.
- [ ] Override always requires a reason.
- [ ] The presenter can disconnect the LLM provider and still complete a rules-only review.
- [ ] The UI clearly identifies synthetic demo status and human responsibility.

---

## 21. Go/no-go gates

### Hackathon demonstration

Go only when:

- Data is synthetic.
- Autonomous decisions are technically impossible.
- Golden tests, audit tests, and safe failure paths pass.
- The product is visibly labeled as a demo.

### Internal pilot

Requires:

- Approved intended use and policy governance
- Formal security/privacy review and threat model
- SSO/MFA and centralized access lifecycle
- Retrieval, groundedness, bias, and failure-mode evaluation
- Retention, deletion, monitoring, incident response, and vendor review
- Approved infrastructure and AI data-handling terms

### Production

Requires, at minimum:

- Managed relational database and durable queue
- Supported server-backed retrieval architecture
- High availability, disaster recovery, monitoring, and penetration testing
- Formal rule/policy/model change approval
- Compliant decision reasons, notices, appeals, and timeliness workflows
- Security, privacy, legal/compliance, clinical/coding, and claims-operations approval

### Immediate no-go conditions

- Real PHI in the demo/local SQLite profile
- Automatic approval or denial
- Unversioned or ineffective-dated policy evidence
- Arbitrary executable rules from database/UI input
- Agent access to decision mutation tools
- Unrestricted cross-member historical retrieval
- Missing audit event for any mutation
- Multiple processes directly writing the same SQLite/Chroma files

---

## 22. Key risks and mitigations

| Risk | Mitigation |
|---|---|
| Scope overwhelms hackathon | Phase gates; three hero flows first; defer enterprise features |
| Multi-agent latency/cost | Parallel safe steps, budgets, deterministic agents, one synthesis call |
| Agents amplify each other's mistakes | Independent evidence, strict schemas, evidence hierarchy, conflict display |
| Policy retrieval finds wrong version | Mandatory payer/plan/date filters and labeled evaluation |
| MiniLM misses medical nuance | Hybrid FTS/vector retrieval, short chunks, evaluation before model changes |
| Prompt injection in documents | Treat content as data, tool allowlists, adversarial golden cases |
| SQLite locking | One owning backend, bounded worker, WAL, short transactions |
| Chroma/index corruption | Versioned atomic activation, backups, rebuild from authoritative sources |
| VSIX becomes too large | Measure artifacts; platform-specific packages; checksummed offline model asset strategy |
| Sidecar blocked by endpoint security | Signed builds, diagnostics, documented allowlisting, clean-machine testing |
| Local audit can be altered by machine owner | Hash chain and verified exports; external append-only sink for production |
| Confidence is misinterpreted | Label as model-reported unless calibrated; never use alone for automation |
| Same DB used by two products concurrently | Both connect to one backend; no direct file access |

---

## 23. Locked decisions and implementation advice

1. **Architecture:** modular monolith, not microservices.
2. **Agent design:** five bounded logical agents plus deterministic orchestrator.
3. **Human control:** all decisions and claim mutations require explicit human action.
4. **System of record:** application SQLite, separate from Chroma persistence.
5. **RAG:** hybrid FTS5 plus Chroma, not vector-only retrieval.
6. **Embeddings:** begin with `sentence-transformers/all-MiniLM-L6-v2`; retain an evaluation-driven replacement path.
7. **Graph:** no generic GraphRAG in the first build. Relational links plus hybrid retrieval cover the defined scenarios. Add graph traversal only after a failed labeled multi-hop case demonstrates need.
8. **LLM providers:** design one adapter interface but implement one provider first.
9. **MCP:** safe resource/tool boundary; agents see read/proposal tools only.
10. **Realtime:** persisted SSE, not WebSockets.
11. **Extension:** desktop-only, platform-specific VSIX with local sidecar and first-run initialization.
12. **Web:** single-node container while SQLite is used.
13. **Test data:** curated golden fixtures first; public synthetic imports second.
14. **Production claim:** the hackathon release is production-shaped, not production-ready.

---

## 24. Reference basis

The implementation team should verify dependency versions and protocol revisions when work begins. Architectural choices in this specification were checked against:

- Chroma client documentation: https://docs.trychroma.com/reference/python/client
- Chroma persistence migration notes: https://docs.trychroma.com/docs/overview/migration
- Chroma configuration reference: https://docs.trychroma.com/reference/server-env-vars
- MiniLM model card: https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2
- MCP specification: https://modelcontextprotocol.io/specification/2025-06-18
- MCP tools: https://modelcontextprotocol.io/specification/2025-06-18/server/tools
- MCP resources: https://modelcontextprotocol.io/specification/2025-06-18/server/resources
- VS Code extension packaging: https://code.visualstudio.com/api/working-with-extensions/publishing-extension
- VS Code webview guidance: https://code.visualstudio.com/api/extension-guides/webview
- VS Code web-extension limitations: https://code.visualstudio.com/api/extension-guides/web-extensions

---

## 25. Final build order

For execution, use this strict priority:

```text
Canonical data + state machines
  -> SQLite + migrations + synthetic golden data
  -> Human-only claim workflow + audit
  -> Deterministic rules
  -> Versioned policy editing + hybrid RAG
  -> Persisted jobs + SSE
  -> MCP tools/resources
  -> Specialist agents
  -> Synthesis + human review
  -> VS Code packaging
  -> React web completion
  -> Security, recovery, performance, and release certification
```

The first compelling milestone is not a chatbot. It is one claim moving from queue to evidence-backed multi-agent review to an explicit human decision with a complete, reproducible audit trail.
