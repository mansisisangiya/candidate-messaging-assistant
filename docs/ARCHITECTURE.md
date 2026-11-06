# Architecture

> **Status: partly implemented.** Built (Steps 1-3): config, health route, models, fixtures and store, SQLite repository, tool registry, `LLMClient` protocol, `FakeLLM`, agent loop. Everything else below (guardrails, injected failure, services, run/approval API, state machine, JSON logging config, UI, OpenAI client) is planned.

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

All transitions go through one function. Anything else raises `InvalidTransition`, returned as HTTP 409.

## API contract

Errors use `{"error": {"code": "...", "message": "..."}}`.

| Method | Path | Body | Success | Errors |
|---|---|---|---|---|
| GET | `/api/health` | none | `{status, llm_provider}` | none |
| GET | `/api/conversations` | none | list with candidate name, job title, preview, latest run status | none |
| GET | `/api/conversations/{id}` | none | conversation, candidate, latest run | 404 |
| POST | `/api/conversations/{id}/drafts` | `{instructions?: str <=500}` | 201 `AgentRun` (`awaiting_approval` or `failed`) | 404, 422 |
| GET | `/api/runs?conversation_id=` | none | run summaries (history) | none |
| GET | `/api/runs/{run_id}` | none | `AgentRun` with steps | 404 |
| POST | `/api/runs/{run_id}/approve` | `{edited_text?: str 1-2000}` | 200 `AgentRun` | 404, 409, 422 |
| POST | `/api/runs/{run_id}/reject` | `{reason: str 3-500}` | 200 `AgentRun` | 404, 409, 422 |

A failed run still returns 201: the run was created and `status: failed` plus `error` is the result.

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

**Injected failure:** a config flag or a designated fixture candidate makes `get_interview_status` raise `ToolUnavailableError`. The agent retries once, then receives an error result and drafts without promising a date. The step is logged as `error` and the UI shows a warning. LLM failure or max steps marks the run `failed`.

**Guardrails:** draft non-empty, at most 1200 characters, no leftover placeholders (`[Name]`, `{{`), no salary or compensation mention unless the recruiter's instructions include it.

## Data layer as built (Step 2)

- `models.py`: all Pydantic models (`extra="forbid"`). Ids are restricted to `[A-Za-z0-9_-]{1,64}`, which also constrains LLM-supplied tool arguments.
- `data/store.py`: `FixtureStore` loads the four JSON files once, validates them, and checks references (candidate->job, interview->candidate, conversation->candidate) and duplicate ids. A bad fixture raises `FixtureError` at startup, not mid-run.
- `db/repo.py`: `RunRepository` (stdlib `sqlite3`, tables `runs` and `steps`, one connection per operation). `update_run` only touches a whitelist of columns and does **not** enforce status transitions; the state machine (Step 4) will own that.
- `agent/tools.py`: `ToolRegistry.execute(name, raw_args)` validates args against the Pydantic input model and returns JSON-able dicts. Errors: `ToolInputError`, `UnknownToolError`, `RecordNotFoundError` (all in `errors.py`). `ToolUnavailableError` exists but nothing raises it until the injected failure is built.
- `DATABASE_PATH` (default `data/app.db`, git-ignored) selects the SQLite file.

## Agent loop as built (Step 3)

- `llm/base.py`: `LLMClient.complete(messages, tools) -> LLMResponse` (Protocol), plus `ChatMessage`, `ToolCall`, `LLMResponse`. A response is either tool calls or final text.
- `llm/fake.py`: `FakeLLM()` uses a fixed policy (get_candidate, get_interview_status, get_job, then a template draft). `FakeLLM(script=[...])` replays given responses or raises given exceptions; tests use it to force bad behaviour.
- `agent/prompt.py`: builds the system and user messages from a conversation. The user message carries `Candidate ID: ...`, which the FakeLLM reads.
- `agent/loop.py`: `run_agent(llm, tools, repo, conversation, instructions)` creates the run, loops at most `MAX_STEPS = 6` LLM calls, and returns the finished `AgentRun`.
  - Tool errors (unknown record, bad arguments, unknown tool) are saved as `error` steps and sent back to the LLM as a tool result, so the model can recover.
  - `ToolUnavailableError` is retried once, then handled the same way.
  - An empty LLM response, `LLMError`, exceeding 6 calls, or any unexpected exception ends the run as `failed` with `error` set. Unexpected exceptions are logged, and the stored message is generic.
  - Steps are saved as they happen.
- The loop sets run status directly via the repository. The state machine and its 409 handling are still to do.

## Planned repo layout

```
backend/app/{main.py, config.py, logging.py, models.py, api/, services/, agent/, llm/, db/, data/fixtures/}
backend/tests/{unit/, integration/, api/}
backend/evals/{cases.yaml, run.py}
frontend/src/{api.ts, types.ts, App.tsx, components/}   frontend/e2e/
.github/workflows/{ci.yml, eval-live.yml}
```

## Known limitations (by design)

No auth, no real sending, synchronous runs, FakeLLM does not demonstrate real model quality, SQLite is single-node only.
