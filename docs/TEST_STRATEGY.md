# Test Strategy

> **Status: all layers implemented** (unit, data validation, integration, API, frontend component, browser E2E, eval harness) and run locally; the CI workflow passed in [one GitHub Actions run](https://github.com/mansisisangiya/candidate-messaging-assistant/actions/runs/42278166770) on commit `6b8cc22` (jobs `backend`, `frontend`, `e2e`). Results are recorded only after they are actually run.

## Principles

- Automated tests are deterministic: they use `FakeLLM` and temporary SQLite databases, never a real LLM or the network.
- A few strong cases per layer, not exhaustive coverage.
- Always cover the injected failure and the invalid-transition (409) case.

## Layers

| Type | Tool | Coverage |
|---|---|---|
| Unit | pytest | Tools return/raise correctly; state machine allows and forbids transitions; guardrails; agent loop with a scripted fake (call order, invalid tool args, max steps) |
| Data validation | pytest | All fixtures parse into Pydantic models; references resolve (conversation -> candidate -> job); bad request bodies rejected (empty reason, over-long edited text) |
| Integration | pytest | DraftingService + real tools + temp SQLite + FakeLLM: run saved with steps; injected failure gives a degraded draft plus an error step |
| API | pytest + FastAPI TestClient | Draft then approve happy path; 404; 409 on double approve; 422 on reject without reason; failed run returns 201 with `failed` |
| Frontend | Vitest + Testing Library (fetch mocked, no network) | API client (envelope, non-JSON error, network failure); DraftPanel per status (draft, buttons and trace; warning banner; failed run with no approve button; too-short reject reason makes no API call; edit vs no edit; 409 shows the message and refreshes); ConversationView (pending state, error alert, 500 limit); App list |
| Browser E2E | Playwright | Backend with `LLM_PROVIDER=fake` plus Vite dev server: select conversation, draft, approve, see "Ready to send". Second test: failure candidate shows the warning |
| AI eval | `backend/evals/run.py` | See below |

## Eval harness

`backend/evals/cases.yaml` holds 14 cases (Step 7, extended in Step 9), each labelled with a required `criterion` (task_completion, groundedness, relevance, tool_accuracy, safety, failure_handling; the tests check every criterion has a case), a conversation, optional instructions, optional env override, an optional scripted LLM and declarative checks (`status`, `contains`, `not_contains`, `max_length`, `step_types`, `error_steps`, `has_draft`, `grounded_in_tools`, `addresses_topic`, `tool_calls`). `python -m evals.run` (or `make eval`) prints PASS/FAIL with the reason per case, a table per criterion and the pass rate, `--repeat N` runs every case N times and lists flaky cases, and exits non-zero below `--threshold` (default 1.0: the fake is deterministic, so every case must pass; a live-model run would use something like 0.8). The harness only prints; [docs/reports/eval-report.md](reports/eval-report.md) is pasted from its real output (no generated markdown report, which was cut).

`tests/evals/test_evals.py` asserts the shipped cases meet the threshold, that results do not depend on the environment (a test sets `INJECT_INTERVIEW_FAILURE_FOR` with `monkeypatch`, another writes it to a `.env` in the working directory) and that the harness can fail: a deliberately wrong case file, an impossible threshold, a crashing case, and three mutations (guardrail disabled, failure injection removed, tool scoping removed) each make it exit non-zero. Further tests cover: every criterion has a case, `criterion` is required, `grounded_in_tools` fails an ungrounded draft (unit test of the check function, plus a harness run that exits non-zero), `addresses_topic` and `tool_calls` failures, and `--repeat` (zero flaky cases for FakeLLM; a simulated flaky case is listed and fails the run).

- CI runs it against `FakeLLM`, which catches regressions in prompts, tools and pipeline.
- A manual live run against a real provider is optional, not built, and not required.

**Limitation: evals against `FakeLLM` validate the pipeline (tools, state, guardrails, degradation, trace shape), not model quality.** The fake writes template text, so a pass says nothing about how a real model would write.

## Which checks run when

| When | Checks | Exists in `.github/workflows` today? |
|---|---|---|
| Every push and pull request | `ruff`; `tsc` (app and e2e code); pytest (unit, data validation, integration, API, plus the eval-harness tests); Vitest; FakeLLM eval at threshold 1.0 (`python -m evals.run`); frontend build; Playwright E2E (2 tests) | **Yes**, in `ci.yml` (jobs `backend`, `frontend`, `e2e`). Passed in [one GitHub Actions run](https://github.com/mansisisangiya/candidate-messaging-assistant/actions/runs/42278166770) on commit `6b8cc22` (an earlier run failed because CI used Node 20; fixed by moving to Node 22) |
| Deployment or release | Everything above, plus a smoke test of the deployed API (`GET /api/health` returns `{"status":"ok"}`) and one E2E test against the deployed stack | **No.** Described only: there is no deployment, so there is no deploy workflow or smoke test |
| Scheduled regression (nightly) | Full suite; a live-model eval with `--repeat 5` and a lower threshold (for example 0.8), with results stored per run to spot model or prompt regressions over time | **No.** Described only: there is no live provider client (the OpenAI client is not built), no schedule and no results store |

## Non-determinism, variance and regressions

- The FakeLLM is deterministic: the same input gives the same output, so the eval, unit and E2E tests are repeatable and any failure is a real regression. That is why the CI eval threshold is 1.0. These evals test the pipeline (tools, state machine, guardrails, failure handling, trace shape), **not model quality**: the fake writes template text.
- A real model varies between runs and between model or prompt versions. Measuring it needs repeated runs per case, per-criterion pass rates (a safety criterion should stay at 100% while a style criterion may tolerate less), a threshold below 1.0 for the noisy criteria, and a stored baseline so a prompt or model change is compared with the previous results instead of eyeballed.
- `--repeat N` is the hook for that: it runs every case N times with fresh state, counts every run in the pass rate and the per-criterion table, and lists cases whose outcome differs between runs. With FakeLLM it must report none, and a test checks that (and checks that a simulated flaky case is listed and fails the run). Storing results over time and comparing to a baseline is not built.
- `addresses_topic` (relevance) is a keyword proxy and `grounded_in_tools` only checks dates, times, interviewer names and job titles it knows about; a live model would need a rubric or LLM-as-judge for relevance, which is not built.

## Why each layer exists (risk-based)

| Layer | The failure it catches |
|---|---|
| Unit | A rule broken in isolation: an illegal state transition allowed, a guardrail that misses a placeholder, a tool accepting bad arguments |
| Data validation | A fixture with a dangling reference or a malformed record that would break every run at load time |
| Integration | Pieces that work alone but not together: the loop, real tools, SQLite and the state machine (steps persisted, run ends in the right state, injected outage degrades) |
| API | Contract regressions: status codes (201, 404, 409, 422), the error envelope, no traceback leaks, the 409 on a second approve |
| Frontend component | A UI that shows the wrong actions for a status, sends a bad request, or hides an API error |
| Browser E2E | Wiring across the real browser, Vite proxy and backend that mocks cannot show (draft, trace, approve, the degraded banner) |
| AI eval | Behaviour regressions that unit tests would not name: an invented date or salary, another candidate's data leaking, a prompt-injected lookup, a missing warning when data was unavailable |

## CI plan (GitHub Actions)

- `backend`: ruff, pytest, fake-LLM eval (`python -m evals.run`; step added in Step 7, workflow passed in [one GitHub run](https://github.com/mansisisangiya/candidate-messaging-assistant/actions/runs/42278166770) on commit `6b8cc22`)
- `frontend`: tsc, vitest, build
- `e2e`: depends on both; installs Playwright Chromium, runs both Playwright tests, uploads the report on failure

## Results

History by step: each 'Not yet covered' refers to that step only. The current status is in the table above and in docs/reports/test-report.md.

- Step 1: `pytest` 1 passed; Vitest 1 passed.
- Steps 2-3: `cd backend && .venv/bin/python -m pytest` gave 41 passed (models, fixture validation, tools, SQLite repository, tools + repository integration); `ruff check .` clean.
- Step 4: `.venv/bin/python -m pytest` gave 65 passed in total (24 new: FakeLLM policy and script mode, loop error handling, retry, max steps, LLM failure, plus integration runs over all four fixture conversations); `ruff check .` clean.
- Step 5: `cd backend && .venv/bin/python -m pytest` gave 128 passed (63 new: the full 5x5 transition matrix and terminal-state rules, stale conditional write rejected, tool retry/crash/too-many-calls handling, prompt fence, candidate scoping, drafting service, API 201/failed-201/404/422/500 envelopes); `ruff check .` clean. Not yet covered: approve/reject (409 on double approve is a Step 6 API test), guardrails, injected failure, eval harness, E2E.
- Step 6: `cd backend && .venv/bin/python -m pytest` gave 188 passed (60 new: every guardrail rule including salary allowed by instructions, failure wrapper, loop test with a scripted LLM that mentions salary, case-insensitive fence strip, request-model stripping, injected failure integration (both error steps, no date) and API, approve as-is/edited, reject, 422/404, and 409 for double approve, approve after reject, reject after approve, approving a failed run, plus a stale approval that loses to a concurrent reject); `ruff check .` clean. Not yet covered: frontend, browser E2E, eval harness.
- Step 7: `cd backend && .venv/bin/python -m pytest` gave 216 passed (28 new: 16 logging tests covering JSON validity, `run_id` on loop logs and cleared afterwards via caplog, state-transition and tool-error logs, and no emails or message text in logs; 12 eval-harness tests including the environment and `.env` hermeticity tests); `ruff check .` clean. `make eval`: 10/10 passed (100%, threshold 100%). Deliberately broken copy of the cases (two wrong expectations): 8/10 = 80% -> FAILED, exit 1. Not yet covered: frontend components, browser E2E.
- Step 8: `make test` gave 216 backend and 20 frontend tests passed (19 new frontend tests: API client 7, DraftPanel 7, ConversationView 4, App 2, replacing the old heading test); `make lint` (ruff, `tsc`) clean; `make build` ok; `make e2e` (Playwright, Chromium): 2 passed, about 3-8 s. The E2E config starts its own backends with temp SQLite files and Vite servers. I also broke an assertion on purpose and confirmed Playwright saved a screenshot, trace and error context in `test-results/`, then restored it. Not covered: a UI history list, cross-browser runs, CI (never run on GitHub).
- Step 9: `make test` gave 231 backend (15 new eval-harness tests) and 20 frontend tests passed; `make lint` clean (now includes the E2E code); `make build` ok; `make eval` 14/14, per-criterion table all full; `make e2e` 2 passed. The complete real output is in [reports/test-report.md](reports/test-report.md) and [reports/eval-report.md](reports/eval-report.md).
