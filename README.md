# Candidate Messaging Assistant

> **Status: Steps 1-6 complete (1 scaffolding, 2 data layer, 3 persistence and tools, 4 FakeLLM and agent loop, 5 state machine, drafting service and read/draft API, 6 injected failure, guardrails and approve/reject).** The whole backend flow works over HTTP: list conversations, create a draft (the agent runs synchronously with `FakeLLM`), read the steps, approve or reject. There is no UI, JSON logging config or eval harness yet. Unticked items under "Planned features" are plans, not working software.

## Objective

An AI-powered assistant that helps a recruiter respond to candidates. A recruiter opens a conversation, asks an AI agent to draft a reply, reviews the draft and the steps the agent took, then approves or rejects it. Approved drafts are marked "ready to send". Nothing is actually sent.

Built as an engineering assessment to demonstrate: an agent that calls tools, state across steps, a backend API with a simple frontend, human approval, error handling with an injected failure, a layered test suite, an AI evaluation harness, logging and execution history, CI, and documentation.

## Planned features

Progress is tracked here. A box is ticked only after the item is implemented and verified by running it.

- [x] Project scaffolding (FastAPI + health endpoint, React/Vite/TS, pytest, Vitest, Makefile, CI workflow)
- [ ] View seeded candidate conversations (UI; the `GET /api/conversations` endpoints are done, see below)
- [ ] Ask the agent to draft a reply (UI; `POST /api/conversations/{id}/drafts` with optional instructions is done)
- [x] Read/draft API with a uniform error envelope (`GET /api/conversations`, `GET /api/conversations/{id}`, `POST /api/conversations/{id}/drafts`, `GET /api/runs`, `GET /api/runs/{id}`); verified with tests and real `curl` calls
- [x] Run state machine (one transition table, conditional write, `InvalidTransition` -> 409)
- [x] Candidate-scoped tools (the LLM cannot read another candidate's data) and a fenced, untrusted transcript in the prompt
- [x] Agent tools: `get_candidate`, `get_interview_status`, `get_job`
- [x] Persistence for agent runs and steps (SQLite repository)
- [x] Pydantic models and validated JSON fixtures (4 candidates, 3 jobs, 4 conversations)
- [x] Persisted multi-step agent run (steps, status, draft): `run_agent` with `FakeLLM`, max 6 LLM calls, runs end `awaiting_approval` or `failed` (not yet reachable over HTTP)
- [x] Approve (optionally edited) or reject (reason required) over the API (`POST /api/runs/{id}/approve|reject`); double approve, approve after reject and approving a failed run return 409; verified with tests and real `curl` calls (no UI yet)
- [x] Injected tool failure with graceful degradation (backend: `INJECT_INTERVIEW_FAILURE_FOR=cand_priya`; verified with tests and a real `curl`; the UI warning is not built)
- [x] Draft guardrails (non-empty, max 1200 characters, no placeholders, no compensation talk unless the recruiter asked); a violation fails the run and the draft is not stored
- [ ] Execution history and trace view
- [ ] Structured JSON logging with run ids
- [ ] Tests: unit, data validation, integration, API, frontend, browser E2E (done so far: unit, data validation, integration and API tests; no frontend, E2E or eval tests yet)
- [ ] Automated AI evaluation harness with pass threshold
- [ ] GitHub Actions CI
- [ ] Optional OpenAI client (not required to run anything)

## Technology

Python 3.12, FastAPI, Pydantic, SQLite, React + TypeScript (Vite), pytest, Vitest, Playwright, GitHub Actions. The default LLM is a deterministic `FakeLLM`, so no API key or network is needed.

## Out of scope

Authentication, actually sending messages, streaming, background job queues, multi-user support, agent frameworks (LangChain etc.), vector databases.

## Documentation

- [CLAUDE.md](CLAUDE.md): conventions and constraints for AI-assisted development
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): architecture, API, agent workflow
- [docs/TEST_STRATEGY.md](docs/TEST_STRATEGY.md): testing approach
- [docs/AI_INTERACTION_LOG.md](docs/AI_INTERACTION_LOG.md): record of AI interactions

## Setup and usage

Requirements: Python 3.12, Node.js 20+ (developed on Node 24), `make`. No OpenAI key is needed.

```bash
make install        # creates backend/.venv, installs backend and frontend dependencies
```

Run (two terminals):

```bash
make backend        # FastAPI on http://localhost:8000
```

```bash
make frontend       # Vite on http://localhost:5173 (proxies /api to :8000)
```

Check the backend: `curl http://localhost:8000/api/health` returns `{"status":"ok","llm_provider":"fake"}`.

Try the API (run state is stored in `backend/data/app.db`, git-ignored):

```bash
curl http://localhost:8000/api/conversations
curl -X POST http://localhost:8000/api/conversations/conv_priya/drafts \
  -H 'content-type: application/json' -d '{"instructions":"Keep it short"}'   # 201, includes steps
curl "http://localhost:8000/api/runs?conversation_id=conv_priya"               # summaries, no steps
curl -X POST http://localhost:8000/api/runs/<run_id>/approve \
  -H 'content-type: application/json' -d '{"edited_text":"Optional edited text"}'   # body optional; 200
curl -X POST http://localhost:8000/api/runs/<run_id>/reject \
  -H 'content-type: application/json' -d '{"reason":"Too formal"}'              # reason 3-500 chars; 200
```

A run that is already approved, rejected or failed cannot be decided again: the API answers `409 invalid_transition`.

**Injected failure demo.** Start the backend with `INJECT_INTERVIEW_FAILURE_FOR=cand_priya make backend`. Then `get_interview_status` always fails for Priya (conversation `conv_priya`; her real interview date is 2026-11-12). The run still ends `awaiting_approval`: two `error` steps (first one ends in "retrying") and a draft that promises no date. Every other candidate is normal; use `conv_tom` for the happy path. A UI can treat "any `error` step in the run" as the warning. The default is off.

Errors always look like `{"error": {"code": "...", "message": "..."}}`. A run that fails (for example the LLM errors) is still returned with `201` and `"status": "failed"`.

Tests and checks:

```bash
make test           # backend (pytest) + frontend (Vitest)
make test-backend
make test-frontend
make lint           # ruff + tsc
make build          # frontend production build
```

Configuration is via environment variables; see `.env.example` (copy to `backend/.env` if you want overrides). All values are optional.
