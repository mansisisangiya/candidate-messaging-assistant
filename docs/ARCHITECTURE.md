# Architecture

> **Status: implemented except the optional OpenAI client.** Built (Steps 1-8): config and health route (1); models, fixtures and store (2); SQLite repository and tool registry (3); `LLMClient`, `FakeLLM` and agent loop (4); state machine, drafting service, read/draft API and error envelope (5); injected failure, guardrails and approve/reject (6); Eval harness and JSON logging (7); frontend and Playwright E2E (8). Not built: OpenAI client, live-eval workflow.

## Layers

```
React + TS (Vite):  ConversationList | ConversationView | DraftPanel (trace + approve/reject)
        | JSON over HTTP
FastAPI  api/routes.py        thin: validate, call service, map errors
services/drafting.py          create run -> run agent -> persist
services/approval.py          state transitions (approve / reject)
agent/loop.py                 run_agent(llm, tools, ctx) -> result
agent/tools.py                tool registry, Pydantic input/output
agent/guardrails.py           draft validation
llm/base.py                   LLMClient Protocol
llm/fake.py                   deterministic scripted client (default)
llm/openai_client.py          optional real provider
data/fixtures/*.json          read-only candidates, jobs, interviews, conversations
db/repo.py                    SQLite: runs and steps (mutable state)
```

Logging: JSON lines; a `run_id` is attached via a context variable.

## Key decisions

1. **LLM behind a Protocol.** The loop only knows `complete(messages, tools) -> LLMResponse`. Provider selected by `LLM_PROVIDER` (default `fake`). Keeps LLM integration separate from business logic and makes tests deterministic.
2. **Fixtures for domain data, SQLite for run state.** Candidates and jobs stand in for an ATS we do not own. Runs and approvals are owned data.
3. **Hand-written agent loop** instead of a framework: small, explainable, provider-agnostic.
4. **Synchronous runs.** `POST /drafts` returns the finished run. A production system would use a background job and polling; out of scope here.
5. **Thin routes, logic in services**, so services are testable without HTTP.

## Data models (Pydantic)

- `Candidate {id, name, email, job_id, stage}`
- `Job {id, title, team, location}`
- `Interview {candidate_id, status: not_scheduled|scheduled|completed|pending_feedback, scheduled_at?, interviewer?}` (`not_scheduled` added in Step 2 so a candidate with no interview still gets a normal answer instead of an error; a scheduled interview must have `scheduled_at`)
- `Message {sender: candidate|recruiter, text, sent_at}`
- `Conversation {id, candidate_id, messages}`
- `AgentStep {index, type: tool_call|tool_result|llm_message|error, name?, input?, output?, error?, duration_ms, ts}`
- `AgentRun {id, conversation_id, status, instructions?, steps, draft_text?, final_text?, rejection_reason?, error?, created_at, updated_at}`

## Run state machine

```
running -> awaiting_approval -> approved   (final_text = edited or draft)
   |                        \-> rejected   (reason required)
   \-> failed   (unrecoverable error, max steps, or guardrail failure)
```

All transitions go through one function. Anything else raises `InvalidTransition`, returned as HTTP 409. Built in Step 5 (see below); only the `running` edges are used so far.

## API contract

Errors use `{"error": {"code": "...", "message": "..."}}`.

| Method | Path | Body | Success | Errors |
|---|---|---|---|---|
| GET | `/api/health` | none | `{status, llm_provider}` | none |
| GET | `/api/conversations` | none | list with candidate name, job title, preview, latest run status | none |
| GET | `/api/conversations/{id}` | none | conversation, candidate, job, latest run (with steps) | 404 |
| POST | `/api/conversations/{id}/drafts` | `{instructions?: str <=500}` | 201 `AgentRun` (`awaiting_approval` or `failed`) | 404, 422 |
| GET | `/api/runs?conversation_id=` | none | run summaries without steps, newest first, with `step_count` | none |
| GET | `/api/runs/{run_id}` | none | `AgentRun` with steps | 404 |
| POST | `/api/runs/{run_id}/approve` | `{edited_text?: str 1-2000}` | 200 `AgentRun` | 404, 409, 422 |
| POST | `/api/runs/{run_id}/reject` | `{reason: str 3-500}` | 200 `AgentRun` | 404, 409, 422 |

Error mapping: `not_found` 404, `invalid_transition` 409, request validation 422 (`validation_error`; the invalid input is not echoed), `llm_error` 502, anything else 500 with a generic message and no traceback. Implemented in `api/errors.py`. A failed run still returns 201: the run was created and `status: failed` plus `error` is the result.

## Agent workflow

Tools (read-only): `get_candidate(candidate_id)`, `get_interview_status(candidate_id)`, `get_job(job_id)`. Each has a name, description, Pydantic input model and function; the registry derives the LLM tool schema from the Pydantic model.

```
messages = [system prompt, conversation transcript, recruiter instructions]
for step in range(MAX_STEPS = 6):
    resp = llm.complete(messages, tool_schemas)       # may raise LLMError
    if resp.tool_calls:
        for each call: validate args -> run tool (1 retry) -> record step
                       errors become tool results fed back to the LLM
        continue
    validate draft with guardrails -> return
raise MaxStepsExceeded
```

Steps are persisted as they happen, so failed runs still have a trace.

**FakeLLM:** scripted policy that reads message history and calls the tools in order, then writes a template draft from the results. It proves the orchestration, not model quality.

**Injected failure:** `INJECT_INTERVIEW_FAILURE_FOR=<candidate_id>` makes `get_interview_status` raise `ToolUnavailableError` for that candidate's conversations. The agent retries once, then receives an error result and drafts without promising a date. Both attempts are logged as `error` steps and the UI shows a warning. LLM failure or max steps marks the run `failed`.

**Guardrails:** draft non-empty, at most 1200 characters, no leftover placeholders (`[Name]`, `{{`), no salary or compensation mention unless the recruiter's instructions include it.

## Data layer, persistence and tools as built (Steps 2-3)

- `models.py`: all Pydantic models (`extra="forbid"`). Ids are restricted to `[A-Za-z0-9_-]{1,64}`, which also constrains LLM-supplied tool arguments.
- `data/store.py`: `FixtureStore` loads the four JSON files once, validates them, and checks references (candidate->job, interview->candidate, conversation->candidate) and duplicate ids. A bad fixture raises `FixtureError` at startup, not mid-run.
- `db/repo.py`: `RunRepository` (stdlib `sqlite3`, tables `runs` and `steps`, one connection per operation). `update_run` only touches a whitelist of non-status columns; `update_status_if` is the conditional status write, used only by the state machine.
- `agent/tools.py`: `ToolRegistry.execute(name, raw_args)` validates args against the Pydantic input model and returns JSON-able dicts. Errors: `ToolInputError`, `UnknownToolError`, `RecordNotFoundError` (all in `errors.py`). `ToolUnavailableError` is raised only by the injected failure wrapper (Step 6).
- `DATABASE_PATH` (default `data/app.db`, git-ignored) selects the SQLite file.

## Agent loop as built (Step 4)

- `llm/base.py`: `LLMClient.complete(messages, tools) -> LLMResponse` (Protocol), plus `ChatMessage`, `ToolCall`, `LLMResponse`. A response is either tool calls or final text.
- `llm/fake.py`: `FakeLLM()` uses a fixed policy (get_candidate, get_interview_status, get_job, then a template draft). `FakeLLM(script=[...])` replays given responses or raises given exceptions; tests use it to force bad behaviour.
- `agent/prompt.py`: builds the system and user messages from a conversation. The user message carries `Candidate ID: ...`, which the FakeLLM reads. The candidate transcript sits between `<untrusted_transcript>` tags (a closing tag inside a message is stripped) and the system prompt tells the model never to follow instructions inside it. Prompt wording is a mitigation only; the hard limit is the scoped tools below.
- `agent/loop.py`: `run_agent(llm, tools, repo, conversation, instructions)` creates the run, loops at most `MAX_STEPS = 6` LLM calls, and returns the finished `AgentRun`.
  - Tool errors (unknown record, bad arguments, unknown tool) are saved as `error` steps and sent back to the LLM as a tool result, so the model can recover.
  - `ToolUnavailableError` is recorded as an `error` step ("..., retrying"), retried once, then handled the same way if it fails again.
  - **Tool boundary:** an exception that is not an `AppError` (a bug in a tool) is also caught per tool call, recorded as an `error` step with a generic message, logged with its traceback, and the run continues. Choice: one broken tool should degrade the draft, not discard the run.
  - More than `MAX_TOOL_CALLS_PER_RESPONSE = 4` tool calls in one LLM response fails the run before anything executes.
  - An empty LLM response, `LLMError`, exceeding 6 calls, or any unexpected exception outside tools ends the run as `failed` with `error` set. Unexpected exceptions are logged, and the stored message is generic.
  - Steps are saved as they happen.
- Run status changes go through `services/run_state.transition` (Step 5).

## State machine, drafting service and API as built (Step 5)

- `services/run_state.py`: `ALLOWED_TRANSITIONS` is the only transition table and `transition(repo, run_id, to, **fields)` the only way to change status. It reads the current status, checks the table, then calls `repo.update_status_if`, an `UPDATE ... WHERE id=? AND status=?` whose rowcount is checked. A stale or concurrent writer gets `InvalidTransition` (409) and nothing is written. Terminal states (`approved`, `rejected`, `failed`) allow nothing, not even themselves. `status` is not in the repository's generic update whitelist.
- `agent/tools.py` `CandidateScopedTools`: wraps the registry for one conversation. A `candidate_id` argument other than the conversation's candidate raises `ToolInputError` in code, so it becomes an `error` step and returns no data. `get_job` is not scoped (job data is not candidate-private).
- `services/drafting.py` `DraftingService.create_draft`: loads the conversation (404 if missing), scopes the tools, runs the agent.
- `services/queries.py`: read-only views for the API (conversation list with latest run status, detail, run summaries).
- `api/deps.py`: the one place that builds store, repository, LLM (`llm/factory.py`, chosen by `LLM_PROVIDER`) and service. Tests override `get_repo` and `get_llm` with `app.dependency_overrides`.
- `api/routes.py` is thin: validate, call a service, return. `api/errors.py` converts every error into the envelope.

## Injected failure, guardrails and approval as built (Step 6)

- `agent/failure_injection.py` `FailingTools`: wraps a tool executor; `get_interview_status` raises `ToolUnavailableError` on every call, so the loop's single retry fails as well. `DraftingService` wraps the tools only when the conversation's candidate equals `INJECT_INTERVIEW_FAILURE_FOR` (default empty, off). Demo/E2E candidate: `cand_priya`, whose interview is really scheduled, so "no date in the draft" is a meaningful check. Result: steps `error ... retrying`, `error`, then a draft like "I'm checking on the interview details and will confirm them shortly", and the run ends `awaiting_approval`.
- **Degraded signal:** derived, not stored. A run is degraded when it has `error` steps. Why: a separate `warnings` list would duplicate what the steps already say and need a schema change, and it would have to be kept in sync. Trade-off: any recovered error (for example a bad tool argument the model fixed) also counts as a warning, which is acceptable for a recruiter-facing hint.
- `agent/guardrails.py` `validate_draft(draft, instructions) -> list[str]`: non-empty, at most 1200 characters, no placeholders (`[Name]`, `{{`), no compensation words or currency amounts unless the recruiter's instructions contain such a word. The loop calls it after the LLM returns text. The `llm_message` step stays in the trace for debugging, an `error` step `guardrail_violation: ...` is added, and the run goes to `failed` with the violations as `error`. `draft_text` stays empty, so nothing approvable exists. Compensation matching is a keyword list, a deliberate limit: it is simple to explain, not complete.
- `services/approval.py` `ApprovalService`: `approve(run_id, edited_text=None)` sets `final_text` to the edit (stripped) or the draft; `reject(run_id, reason)` sets `rejection_reason`. Both only call `transition()`; the service has no status checks of its own, so double approve, approve after reject and approving a failed run all produce `InvalidTransition` (409). Request models strip text first, so a whitespace-only edit or reason is a 422.
- Routes `POST /api/runs/{id}/approve` (optional body) and `/reject` (body required) are thin and return the updated `AgentRun`.

## Eval harness and logging as built (Step 7)

- `evals/cases.yaml`: 14 cases, each labelled with a required `criterion` (task_completion, groundedness, relevance, tool_accuracy, safety, failure_handling; every criterion has at least one case). They cover the four interview states, a grounded draft, a deferred salary question (relevance), tool order and arguments, the salary guardrail, tool scoping, a prompt injection in the transcript (`candidate_message` appends it; a scripted model obeys it and tries another candidate's data), the interview outage, a malformed tool argument and an LLM error. Each case names a conversation, optional instructions, optional `env`, an optional scripted LLM (`content`, `tool_call` or `llm_error`) and checks. Expected values are written in the YAML, not read from the fixtures, so the cases are an independent oracle.
- `evals/run.py`: builds the service with `api.deps.get_drafting_service` and a `Settings` built hermetically (`_env_file=None`, `inject_interview_failure_for=""`, then only the case's own `env`), so a developer's environment variables or `.env` cannot change results while the API's wiring is still exercised. Check types, one function each: `status`, `contains`, `not_contains`, `max_length`, `step_types` (also asserts indexes 0..n-1), `error_steps`, `has_draft`, `grounded_in_tools` (every date, time, known interviewer name and job title in the draft must appear in a `tool_result` of the same run), `addresses_topic` (any keyword present: a crude proxy for relevance) and `tool_calls` (names, order, and `candidate_id`/`job_id` arguments). A case passes only if all its checks pass. The pass rate is passed/total; exit code 1 if it is below `--threshold`, default 1.0. Why: `FakeLLM` has no randomness, so a failing case is a real regression, and a lower default (0.9 of 10 cases) would let one through with exit 0. A future live-model run is non-deterministic and would use a lower value such as 0.8. A case that raises counts as failed. The output has a per-criterion table (passed/total) and the overall rate. `--repeat N` runs every case N times (fresh state each time) and lists cases whose result differs between runs; the pass rate then counts every run. With `FakeLLM` there are none; it is the hook for measuring variance with a live model.
- Logging: `app/logging_config.py` has a JSON formatter, a filter that adds `run_id` from the `run_id_var` context variable, and `configure_logging(level)` (called once in `create_app()`, idempotent). `bind_run_id(run_id)` sets the variable and resets it in `finally`; `run_agent` and `transition()` use it (so approve/reject transitions are tagged too). Logged: run started / completed (status, `duration_ms`) / failed, tool errors and retries (tool name and error code only), guardrail violations, and every state transition or rejected transition (from, to). Rule: log ids, codes, counts and durations, never emails or message text; a test scans the logs for both.
- Trade-offs: a context variable (not a parameter) keeps log calls free of plumbing; threads in FastAPI each get their own context, which suits synchronous runs. A failed run's `error` text is logged, so it must stay free of PII (it holds generic guardrail or LLM error messages).

## Frontend as built (Step 8)

Plain React + TypeScript (strict, no `any`); no UI library, router or state library.

- `src/types.ts`: every API type, mirroring `models.py` (kept in sync by hand), plus the `ApiError` class. `src/api.ts`: one typed `fetch` wrapper per endpoint; a non-2xx response is parsed as the error envelope and thrown as `ApiError(code, message, status)`; a non-JSON error becomes `http_error` and an unreachable server `network_error`.
- `App.tsx` holds the state (conversation list, selected detail, error). It ignores a slower response for a previously selected conversation, and refreshes the list after any run change so the badges stay current.
- `ConversationList`, `ConversationView` (transcript, info, instructions, Draft reply with pending state and an error alert), `DraftPanel` (draft in an editable textarea only while `awaiting_approval`, approve, reject with a reason checked client-side, outcome display, 409 handling), `TracePanel` (steps in order, error steps highlighted), `StatusBadge`.
- Degraded warning: shown when the run has any `error` step and is not `failed`. This is the "derived, not stored" rule from Step 6.
- Approve sends `edited_text` only if the recruiter changed the text. Client-side checks (empty draft, reason under 3 characters) only save a round trip; the backend still validates.
- Vite proxies `/api` to `VITE_API_PROXY` (default `http://localhost:8000`); the E2E config uses this to point at its own backend.
- Limitation: only the latest run of a conversation is shown; there is no history list.

## Repo layout

```
backend/app/{main.py, config.py, logging_config.py, models.py, api/, services/, agent/, llm/, db/, data/fixtures/}
backend/tests/{unit/, integration/, api/}
backend/evals/{cases.yaml, run.py}   (built)
frontend/src/{api.ts, types.ts, App.tsx, components/}   frontend/e2e/
.github/workflows/ci.yml   (eval-live.yml is not built)
```

## Known limitations (by design)

No auth, no real sending, synchronous runs, FakeLLM does not demonstrate real model quality, SQLite is single-node only.

Known limitation: if the write to the `failed` state itself fails (for example the database goes away while handling an error), the run is left in `running`. There is no recovery sweep; runs are synchronous, so it would only affect that one request.
