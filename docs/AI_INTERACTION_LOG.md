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
**Outcome:** Verified by running: 128 backend tests passed, ruff clean, and a real `curl` against uvicorn: `POST /drafts` 201 with 7 steps, unknown conversation 404 envelope, 501-character instructions 422 envelope, conversation and run lists. Accepted and committed as `1179e6c`.

## 7. Step 6: injected failure, guardrails, approve/reject
**Model:** Sonnet 5.5
**Prompt (summary):** Three small fixes first (case-insensitive fence strip, blank `instructions` to `None`, a known-limitations line). Then an injected `get_interview_status` failure chosen by `INJECT_INTERVIEW_FAILURE_FOR`, draft guardrails that fail the run, approve/reject services and routes with 409/404/422 behaviour, tests and docs. No frontend, logging config or evals.
**AI output:** `agent/failure_injection.py`, `agent/guardrails.py`, `services/approval.py`, two routes, `ApproveRequest`/`RejectRequest`, a `GuardrailViolationError`, a config setting, and 60 new tests.
**Decisions and changes:**
- Degraded runs are derived from `error` steps instead of a stored `warnings` list: no schema change and nothing to keep in sync. The cost is that any recovered error also shows the warning.
- Failure demo candidate is `cand_priya` because her interview really has a date, so "the draft makes no date promise" is a real check.
- Guardrail failure keeps the text in the `llm_message` step for debugging but leaves `draft_text` empty, so nothing approvable is stored.
- I made the fence-tag strip a regex that also tolerates spaces (`</ untrusted_transcript >`), slightly beyond "case-insensitive".
- The approval service has no status checks; it relies on `transition()` so 409s have one source.
- Replaced the weak "does not invent compensation" test, which only checked that the default FakeLLM does not say "salary", with a scripted LLM that does say it and must fail the run. The old assertion is kept as a separate, honestly named test.
- My first approval API test used a 2-character rejection reason and got 422 instead of 409; the test was wrong, not the code, so I changed the test.
- Ruff asked for the `pydantic` import in `models.py` to be reformatted; applied.
**Outcome:** Verified by running: 188 backend tests passed, ruff clean, and a real `curl` against uvicorn with `INJECT_INTERVIEW_FAILURE_FOR=cand_priya`: two error steps, no date in the draft, `awaiting_approval`; `conv_tom` unaffected; approve edited 200; second approve 409; reject after approve 409; short reason 422; unknown run 404. Accepted and committed as `26728f2`.

## 8. Step 7: eval harness and JSON logging
**Model:** Sonnet 5.5
**Prompt (summary):** A YAML-driven eval harness with 8-10 meaningful cases, a pass threshold and non-zero exit, a pytest wrapper, `make eval` and a CI step; stdlib JSON logging with a `run_id` context variable, logging of runs, tool errors, guardrails and transitions, and no PII. No markdown report, live-eval workflow or frontend.
**AI output:** `app/logging_config.py`, `evals/{cases.yaml,run.py}`, `tests/evals/test_evals.py`, `tests/unit/test_logging.py`, logging calls in the loop and `transition()`, a `LOG_LEVEL` Literal, a Makefile target, a CI step.
**Decisions and changes:**
- Added `pyyaml` to `requirements.txt` because the cases are YAML; it is the only new dependency (logging uses the stdlib only).
- `bind_run_id` is a context manager (set, then reset in `finally`) instead of bare `set`/`reset` calls, and `transition()` uses it too so approve/reject logs carry the run id. `run_agent` does not set it by hand beyond that.
- The harness builds the service through `api.deps.get_drafting_service` with a `Settings` from the case's env, so the case that injects the failure exercises the real wiring, not a test-only path.
- The harness caught a mistake in my own first draft of a case: I asserted a rejected draft's text was absent from the whole run, but the `llm_message` step keeps it on purpose for debugging. I replaced that check with a new `has_draft` check (the draft is not stored). This was the first real failure the harness reported (9/10, which still passed at the then-default 0.9 threshold; that default is now 1.0, see entry 9).
- Showing the harness can fail: a copy of the cases with two wrong expectations gave 8/10 = 80% and exit 1; tests also break the guardrail and the failure injection on purpose and expect the eval to fail.
- The caplog test needs `RunIdFilter` installed on caplog's handler, because the filter lives on our handler; other logging tests parse the JSON that `configure_logging` writes.
- I suppress logging during the eval run (restored afterwards) so the report stays readable.
**Outcome:** Verified by running: 216 backend tests passed (after the entry 9 fixes; 213 before), ruff clean, `make eval` 10/10, and a real uvicorn run whose stderr was JSON lines with `run_id` on loop and transition logs. Accepted and committed as `6f1137d` together with the entry 9 fixes.

## 9. Step 7 review fixes: hermetic eval, threshold 1.0
**Reviewer finding:** with `INJECT_INTERVIEW_FAILURE_FOR=cand_priya` set in the shell, the eval dropped to 8/10 and exited 1, because `Settings(**case.env)` still read the environment and `backend/.env`. The same could happen for a developer with a copied `.env.example`, or in CI. I reproduced it first with new tests (env var, `.env` file in the working directory, default threshold), which failed before the fix.
**Changes:**
- Settings for each case are built with `_env_file=None` and `inject_interview_failure_for=""` as the base, then only the case's own overrides (merged in a dict; my first version passed the keyword twice and crashed for the outage case, caught by running it). Init values beat environment variables, so every case starts from known defaults.
- Default threshold changed from 0.9 to 1.0. My earlier note that I "kept your default" was not a rationale: with a deterministic fake and 10 cases, 0.9 lets one real regression through with exit 0. A live-model run would use a lower threshold such as 0.8 (not built).
- Correction: my Step 7 report said the real `make eval` output was in the README, but the block was empty (my capture command used a `sed` pattern that does not work on macOS). It is now filled from an actual run.
**Outcome:** see the Step 7 results in TEST_STRATEGY.md. Accepted and committed as `6f1137d`.

## 10. Step 8: minimal frontend and Playwright E2E
**Model:** Sonnet 5.5
**Prompt (summary):** Typed API client, five plain components (list, conversation view, draft panel with approve/reject, trace panel inside it), component tests with mocked fetch, one Playwright test for the main workflow (plus a second for the injected failure if cheap), `make e2e`, an `e2e` CI job, a screenshot, docs. No UI library, router or state library; no backend changes unless blocked.
**AI output:** `frontend/src/{types,api}.ts`, `components/*`, `App.tsx`, `styles.css`, 19 new Vitest tests, `playwright.config.ts`, `e2e/{workflow,failure}.spec.ts`, Makefile target, CI job, docs.
**Decisions and changes:**
- The first message of this step ended at item 1, so I built and reported only the API client and types, then continued when the full brief arrived.
- The second E2E (injected failure) was cheap enough: the config starts a second backend and Vite server on other ports, each project pointing at its own stack. I kept it.
- Added `VITE_API_PROXY` to `vite.config.ts` (a small change not in the brief) so the E2E stacks use ports 8100/8101 and 5174/5175 and never collide with a dev server on 8000/5173.
- Vitest would have picked up the Playwright specs, so its `include` is limited to `src/**`.
- Approve sends `edited_text` only when the text changed, so an unedited approval keeps `final_text` equal to the draft exactly.
- On a 409 the panel shows the API message and re-fetches the run, as asked.
- The `ApiError` class lives in `types.ts` (the brief wanted it with the types).
- Rejected/not done: a run-history list in the UI. The brief asked for the trace of the latest run, which is what exists, so I split the README item and left history unticked rather than tick something the UI does not do.
- A first selector in the E2E (`getByRole("textbox", { name: /draft/i })`) would have matched the instructions box too; I used the draft box's full label. In the App test I removed a click that would have rendered the detail view from the wrong mocked shape.
- Playwright can only be proven useful if it can fail: I broke an assertion on purpose, saw the failure with a screenshot, trace and error context saved, and restored it.
**Outcome:** Verified by running: 216 backend and 20 frontend tests passed, ruff and `tsc` clean, `make build` ok, `make e2e` 2 passed; the screenshot in `docs/screenshots/draft-panel.png` was captured by the E2E test. Pending the user's review.

<!-- Add new entries below. Format: number, title, prompt summary, AI output, outcome (accepted / modified / rejected, and why). -->
