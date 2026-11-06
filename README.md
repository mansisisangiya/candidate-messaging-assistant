# Candidate Messaging Assistant

> **Status: Step 1 (scaffolding) complete.** The backend serves `GET /api/health` and the frontend renders a placeholder page. No agent functionality exists yet. Unticked items under "Planned features" are plans, not working software.

## Objective

An AI-powered assistant that helps a recruiter respond to candidates. A recruiter opens a conversation, asks an AI agent to draft a reply, reviews the draft and the steps the agent took, then approves or rejects it. Approved drafts are marked "ready to send". Nothing is actually sent.

Built as an engineering assessment to demonstrate: an agent that calls tools, state across steps, a backend API with a simple frontend, human approval, error handling with an injected failure, a layered test suite, an AI evaluation harness, logging and execution history, CI, and documentation.

## Planned features

Progress is tracked here. A box is ticked only after the item is implemented and verified by running it.

- [x] Project scaffolding (FastAPI + health endpoint, React/Vite/TS, pytest, Vitest, Makefile, CI workflow)
- [ ] View seeded candidate conversations
- [ ] Ask the agent to draft a reply (with optional recruiter instructions)
- [ ] Agent tools: `get_candidate`, `get_interview_status`, `get_job`
- [ ] Persisted multi-step agent run (steps, status, draft)
- [ ] Approve (optionally edited) or reject (reason required)
- [ ] Injected tool failure with graceful degradation
- [ ] Execution history and trace view
- [ ] Structured JSON logging with run ids
- [ ] Tests: unit, data validation, integration, API, frontend, browser E2E
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

Tests and checks:

```bash
make test           # backend (pytest) + frontend (Vitest)
make test-backend
make test-frontend
make lint           # ruff + tsc
make build          # frontend production build
```

Configuration is via environment variables; see `.env.example` (copy to `backend/.env` if you want overrides). All values are optional.
