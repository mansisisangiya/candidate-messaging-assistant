# AI Interaction Log

A record of actual interactions with the AI assistant (Claude Code) during this assessment. Entries are added as work progresses. Each entry covers what was asked, what the AI proposed, and what was accepted, changed or rejected.

Note: the session switched models between entries 1 and 2 (Opus 5.5 for planning, then Sonnet 5.5).

---

## 1. Requirements analysis and architecture plan
**Model:** Opus 5.5
**Prompt (summary):** Act as a senior mentor. Analyse the assessment requirements, define the minimum viable scope, architecture, API contracts, agent workflow, tool interfaces, test strategy and a 2-4 hour plan. No code yet. No overengineering.
**AI output:** A written plan covering: scope, layered architecture, Pydantic models, a run state machine (`running -> awaiting_approval -> approved|rejected`, `running -> failed`), 8 API endpoints, a hand-written tool-calling loop with 3 read-only tools, a deterministic FakeLLM, an injected tool failure, a test matrix, an eval harness design, CI jobs and an 11-step timeline with cut lines.
**Outcome:** Accepted as the baseline. Open questions about LLM provider and runtime versions were raised for the user.

## 2. Decisions and project setup docs
**Model:** Sonnet 5.5
**Prompt (summary):** Decisions: FakeLLM is the default (no OpenAI key available); keep the `LLMClient` Protocol; OpenAI client only if straightforward and never required; skip live integration test; Python 3.12 + Node 20. Then: create CLAUDE.md, AI_INTERACTION_LOG.md, README.md, ARCHITECTURE.md and TEST_STRATEGY.md before any implementation.
**AI output:** The five documentation files. No application code.
**Outcome:** Accepted by the user, who then asked to start implementation.

## 3. Step 1: project scaffolding
**Model:** Sonnet 5.5
**Prompt (summary):** Create a Desktop folder named for the app and move the docs there. Scaffold FastAPI backend (venv, requirements, config, `GET /api/health`, pytest + health test), React/TS/Vite frontend (Vitest, Testing Library, one test), `.gitignore`, `.env.example`, Makefile, basic CI. No agent code, no unnecessary dependencies, runnable without an OpenAI key.
**AI output:** Project at `~/Desktop/candidate-messaging-assistant`; backend and frontend scaffolds; config files; CI workflow; README setup section.
**Changes made during the session:**
- Pytest printed a deprecation warning (Starlette's TestClient with `httpx`). Switched the dev dependency to `httpx2`; warning gone.
- Ruff flagged `Depends(...)` in a default argument (B008). Changed the route to the `Annotated[...]` style.
- Removed `@testing-library/user-event` after installing it, since nothing uses it yet (it can be added back in the frontend step).
**Outcome:** Verified by running: backend pytest 1 passed, ruff clean, frontend Vitest 1 passed, `tsc` clean, Vite build succeeded, live `curl` of `/api/health` returned 200. CI workflow was written but has not been run on GitHub.

## 4. Steps 2-3: data layer, persistence and read-only tools (built together)
**Model:** Sonnet 5.5
**Prompt (summary):** Review the docs and Step 1 code, then build Pydantic models, SQLite persistence for runs and steps, JSON fixtures, the three read-only tools, validation and error handling, plus unit and integration tests. No agent loop, LLM, approval workflow or frontend. Update README and this log.
**AI output:** `models.py`, `errors.py`, `data/store.py` with four fixture files, `db/repo.py`, `agent/tools.py`, `tests/` (unit and integration), docs updates.
**Decisions and changes:**
- Added `not_scheduled` to the interview status enum (deviation from the original design) so a candidate with no interview gets a normal answer, not an error.
- Added a `DATABASE_PATH` setting; the config file was the only Step 1 file modified.
- Replaced a `model_post_init` validator with a pydantic `model_validator` after reviewing it; ruff removed an unneeded `noqa`.
- Left status-transition enforcement out of the repository on purpose; it belongs to the state machine (Step 5).
- Injected failure not implemented; only the `ToolUnavailableError` class exists.
**Outcome:** Accepted and committed. Verified by running: 41 backend tests passed, ruff clean.

## 5. Step 4: FakeLLM and agent loop
**Model:** Sonnet 5.5
**Prompt (summary):** Define a clean LLM interface, a FakeLLM, and a hand-written agent loop (max 6 steps) that calls the three tools with validated arguments, persists runs and steps in SQLite, and handles tool failures and invalid LLM responses. Unit and integration tests with deterministic responses. No approval or frontend work.
**AI output:** `llm/base.py`, `llm/fake.py`, `agent/prompt.py`, `agent/loop.py`, two new error classes, three test files, docs updates.
**Decisions and changes:**
- FakeLLM has two modes (fixed policy, and a scripted mode for tests) instead of separate test doubles.
- "6 steps" is implemented as 6 LLM calls; a response may contain several tool calls.
- Tool errors go back to the LLM as tool results; only `ToolUnavailableError` is retried.
- A catch-all handler marks the run `failed` so no run stays `running`; the stored message hides internal details.
- Draft guardrails were not requested and are not implemented. Run status is set directly, not through a state machine.
- Ruff removed an unneeded `noqa` and one leftover no-op line was deleted from the loop after review.
**Outcome:** Accepted and committed. Verified by running: 65 backend tests passed, ruff clean. Reviewer feedback on this step led to the fixes in entry 6.

## 6. Step 5: review fixes, state machine, drafting service and read/draft API
**Model:** Sonnet 5.5
**Prompt (summary):** Commit Step 4 separately; fix numbering drift in the docs; apply review fixes to the loop; add a state machine with conditional writes and 409; a drafting service with candidate-scoped tools; thin read/draft routes with a uniform error envelope; tests; docs. No approve/reject, guardrails, injected failure, frontend or logging config.
**Reviewer-driven fixes (from review of Step 4):**
- The first `ToolUnavailableError` is now recorded as an `error` step before the retry (it was silent). The test that asserted "no error step" was changed to assert the new trace.
- Non-`AppError` exceptions at the tool boundary are recorded and the run continues (previously the whole run failed).
- Tool calls per LLM response are capped at 4; exceeding fails the run before executing anything.
- The transcript is fenced as untrusted in the prompt. I also strip a closing fence tag from candidate text, which was not in the request, so a message cannot close the fence.
**AI output:** `services/run_state.py`, `services/drafting.py`, `services/queries.py`, `api/deps.py`, `api/errors.py`, `api/routes.py`, `llm/factory.py`, `CandidateScopedTools`, a conditional status write and `list_run_summaries` in the repository, new models, and 63 new tests.
**Decisions and changes:**
- Kept `update_run` for non-status columns and added `update_status_if`, so `status` cannot be written except through the state machine.
- Added `job` to the conversation detail response (the architecture listed conversation, candidate and latest run) so the UI will not need a second call; documented in ARCHITECTURE.md.
- Scoped `get_candidate` and `get_interview_status` to the conversation's candidate; `get_job` is deliberately not scoped.
- Added a handler for Starlette HTTP errors so unknown paths also use the envelope.
- My first draft of the 500-envelope test was muddled (it set up a scripted LLM it then discarded). I rewrote it to fail the repository dependency instead.
- Rejected: moving the `status -> HTTP` mapping onto the exception classes; it stays in `api/errors.py` so domain errors do not know about HTTP.
**Outcome:** Verified by running: 128 backend tests passed, ruff clean, and a real `curl` against uvicorn: `POST /drafts` 201 with 7 steps, unknown conversation 404 envelope, 501-character instructions 422 envelope, conversation and run lists. Pending the user's review.

<!-- Add new entries below. Format: number, title, prompt summary, AI output, outcome (accepted / modified / rejected, and why). -->
