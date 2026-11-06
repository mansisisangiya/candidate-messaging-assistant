# Test Strategy

> **Status: partly implemented.** Tests exist for the health route, the Step 2 data layer and tools, and the Step 3 FakeLLM and agent loop. Other layers are still planned. Results are recorded only after they are actually run.

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

`evals/cases.yaml` will hold about 6 cases, each with: conversation and instructions, `expected_tools`, `must_include` (e.g. candidate first name, interview date), `must_not_include` (salary, another candidate's name), `max_length`.

Deterministic scorers: tool recall, fact inclusion, forbidden content, guardrail pass. The harness writes a JSON report (markdown optional) and exits non-zero below a pass threshold.

- CI runs it against `FakeLLM`, which catches regressions in prompts, tools and pipeline.
- A manual live run against a real provider is optional and not required.

Limitation: evals against the fake validate the pipeline, not model quality. This will be stated in the README.

## CI plan (GitHub Actions)

- `backend`: ruff, pytest, fake-LLM eval
- `frontend`: tsc, vitest, build
- `e2e`: depends on both; installs Playwright Chromium

## Results

- Step 1: `pytest` 1 passed; Vitest 1 passed.
- Step 2: `cd backend && .venv/bin/python -m pytest` gave 41 passed (models, fixture validation, tools, SQLite repository, tools + repository integration); `ruff check .` clean.
- Step 3: `.venv/bin/python -m pytest` gave 65 passed in total (24 new: FakeLLM policy and script mode, loop error handling, retry, max steps, LLM failure, plus integration runs over all four fixture conversations); `ruff check .` clean.
