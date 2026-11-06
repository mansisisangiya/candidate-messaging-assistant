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

## 4. Step 2: data layer and read-only tools
**Model:** Sonnet 5.5
**Prompt (summary):** Review the docs and Step 1 code, then build Pydantic models, SQLite persistence for runs and steps, JSON fixtures, the three read-only tools, validation and error handling, plus unit and integration tests. No agent loop, LLM, approval workflow or frontend. Update README and this log.
**AI output:** `models.py`, `errors.py`, `data/store.py` with four fixture files, `db/repo.py`, `agent/tools.py`, `tests/` (unit and integration), docs updates.
**Decisions and changes:**
- Added `not_scheduled` to the interview status enum (deviation from the original design) so a candidate with no interview gets a normal answer, not an error.
- Added a `DATABASE_PATH` setting; the config file was the only Step 1 file modified.
- Replaced a `model_post_init` validator with a pydantic `model_validator` after reviewing it; ruff removed an unneeded `noqa`.
- Left status-transition enforcement out of the repository on purpose; it belongs to the Step 4 state machine.
- Injected failure not implemented; only the `ToolUnavailableError` class exists.
**Outcome:** Verified by running: 41 backend tests passed, ruff clean. Pending the user's review.

<!-- Add new entries below. Format: number, title, prompt summary, AI output, outcome (accepted / modified / rejected, and why). -->
