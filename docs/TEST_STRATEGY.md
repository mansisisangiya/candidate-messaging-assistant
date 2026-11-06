# Test Strategy

> **Status: partly implemented.** Tests exist for the health route, the Step 2-3 data layer, persistence and tools, the Step 4 FakeLLM and agent loop, the Step 5 state machine and read/draft API, and the Step 6 injected failure, guardrails and approve/reject. Other layers are still planned. Results are recorded only after they are actually run.

## Principles

- Automated tests are deterministic: they use `FakeLLM` and temporary SQLite databases, never a real LLM or the network.
- A few strong cases per layer, not exhaustive coverage.
- Always cover the injected failure and the invalid-transition (409) case.

## Layers

| Type | Tool | Planned coverage |
|---|---|---|
| Unit | pytest | Tools return/raise correctly; state machine allows and forbids transitions; guardrails; agent loop with a scripted fake (call order, invalid tool args, max steps) |
| Data validation | pytest | All fixtures parse into Pydantic models; references resolve (conversation -> candidate -> job); bad request bodies rejected (empty reason, over-long edited text) |
| Integration | pytest | DraftingService + real tools + temp SQLite + FakeLLM: run saved with steps; injected failure gives a degraded draft plus an error step |
| API | pytest + FastAPI TestClient | Draft then approve happy path; 404; 409 on double approve; 422 on reject without reason; failed run returns 201 with `failed` |
| Frontend | Vitest + Testing Library | DraftPanel shows the right actions per status; reject requires a reason |
| Browser E2E | Playwright | Backend with `LLM_PROVIDER=fake` plus Vite dev server: select conversation, draft, approve, see "Ready to send". Second test: failure candidate shows the warning |
| AI eval | `backend/evals/run.py` | See below |

## Eval harness

`backend/evals/cases.yaml` holds 10 cases (built in Step 7), each with a conversation, optional instructions, optional env override, an optional scripted LLM and declarative checks (`status`, `contains`, `not_contains`, `max_length`, `step_types`, `error_steps`, `has_draft`). `python -m evals.run` (or `make eval`) prints PASS/FAIL with the reason per case and the pass rate, and exits non-zero below `--threshold` (default 1.0: the fake is deterministic, so every case must pass; a live-model run would use something like 0.8). No markdown or JSON report is produced (cut).

`tests/evals/test_evals.py` asserts the shipped cases meet the threshold, that results do not depend on the environment (a test sets `INJECT_INTERVIEW_FAILURE_FOR` with `monkeypatch`, another writes it to a `.env` in the working directory) and that the harness can fail: a deliberately wrong case file, an impossible threshold, a crashing case, and two mutations (guardrail disabled, failure injection removed) each make it exit non-zero.

- CI runs it against `FakeLLM`, which catches regressions in prompts, tools and pipeline.
- A manual live run against a real provider is optional, not built, and not required.

**Limitation: evals against `FakeLLM` validate the pipeline (tools, state, guardrails, degradation, trace shape), not model quality.** The fake writes template text, so a pass says nothing about how a real model would write.

## CI plan (GitHub Actions)

- `backend`: ruff, pytest, fake-LLM eval (`python -m evals.run`; step added in Step 7, workflow not yet run on GitHub)
- `frontend`: tsc, vitest, build
- `e2e`: depends on both; installs Playwright Chromium

## Results

- Step 1: `pytest` 1 passed; Vitest 1 passed.
- Steps 2-3: `cd backend && .venv/bin/python -m pytest` gave 41 passed (models, fixture validation, tools, SQLite repository, tools + repository integration); `ruff check .` clean.
- Step 4: `.venv/bin/python -m pytest` gave 65 passed in total (24 new: FakeLLM policy and script mode, loop error handling, retry, max steps, LLM failure, plus integration runs over all four fixture conversations); `ruff check .` clean.
- Step 5: `cd backend && .venv/bin/python -m pytest` gave 128 passed (63 new: the full 5x5 transition matrix and terminal-state rules, stale conditional write rejected, tool retry/crash/too-many-calls handling, prompt fence, candidate scoping, drafting service, API 201/failed-201/404/422/500 envelopes); `ruff check .` clean. Not yet covered: approve/reject (409 on double approve is a Step 6 API test), guardrails, injected failure, eval harness, E2E.
- Step 6: `cd backend && .venv/bin/python -m pytest` gave 188 passed (60 new: every guardrail rule including salary allowed by instructions, failure wrapper, loop test with a scripted LLM that mentions salary, case-insensitive fence strip, request-model stripping, injected failure integration (both error steps, no date) and API, approve as-is/edited, reject, 422/404, and 409 for double approve, approve after reject, reject after approve, approving a failed run, plus a stale approval that loses to a concurrent reject); `ruff check .` clean. Not yet covered: frontend, browser E2E, eval harness.
- Step 7: `cd backend && .venv/bin/python -m pytest` gave 216 passed (28 new: 16 logging tests covering JSON validity, `run_id` on loop logs and cleared afterwards via caplog, state-transition and tool-error logs, and no emails or message text in logs; 12 eval-harness tests including the environment and `.env` hermeticity tests); `ruff check .` clean. `make eval`: 10/10 passed (100%, threshold 100%). Deliberately broken copy of the cases (two wrong expectations): 8/10 = 80% -> FAILED, exit 1. Not yet covered: frontend components, browser E2E.
