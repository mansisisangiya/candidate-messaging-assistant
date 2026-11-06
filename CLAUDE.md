# CLAUDE.md

Instructions for AI-assisted development on this project. Follow them for all implementation work.

## Project overview

**Candidate Messaging Assistant**: an AI agent that helps a recruiter draft replies to candidate conversations. The agent retrieves candidate, interview and job data through tools, produces a draft, and a human approves or rejects it before it is marked "ready to send". Nothing is actually sent.

This is a 2-4 hour engineering assessment for an AI Full Stack Engineer role. Priorities: clarity, explainability in an interview, and breadth of engineering practice (tests, evals, logging, CI, docs). Not feature richness.

**Status tracking:** README.md has the planned-vs-done checklist. Only tick an item after it is implemented and verified by running it.

## Technology stack

- Backend: Python 3.12, FastAPI, Pydantic v2, SQLite (stdlib `sqlite3`), JSON fixtures
- Frontend: React + TypeScript (Vite), Node 20
- Tests: pytest, Vitest (+ Testing Library), Playwright
- Lint/type: ruff (backend), tsc (frontend)
- CI: GitHub Actions
- LLM: `FakeLLM` is the default. An OpenAI client is optional and never required to run the app or tests.

## Architecture principles

1. **LLM behind a Protocol.** The agent loop depends only on `LLMClient.complete(messages, tools) -> LLMResponse`. Provider is chosen by config (`LLM_PROVIDER=fake|openai`, default `fake`). No provider SDK import outside `llm/`.
2. **Thin routes, logic in services.** Routes validate input, call a service, map errors to the error envelope. No business logic in routes.
3. **Hand-written agent loop.** No LangChain/LangGraph. The loop is small enough to explain line by line.
4. **Read-only domain data in JSON fixtures; mutable run state in SQLite.**
5. **Explicit state machine** for runs, with all transitions enforced in one place. Invalid transitions raise an error that the API returns as 409.
6. **Every run is traceable.** Agent steps are persisted as they happen, and logs carry a `run_id`.
7. **Synchronous agent runs.** No queues or background workers (documented as a trade-off).

## Coding conventions

- Type hints everywhere in Python; Pydantic models for all data crossing a boundary (API, tools, fixtures, LLM responses).
- TypeScript `strict` mode; no `any`. API types live in one file.
- Small functions, descriptive names, comments only for the "why".
- Consistent error envelope: `{"error": {"code": "...", "message": "..."}}`.
- Use stdlib `logging` with structured (JSON) output; never `print` in app code.
- No secrets in the repo. Config via environment variables with safe defaults.

## Testing requirements

- Automated tests must be **deterministic** and use `FakeLLM`. They must never call a real LLM or the network.
- Cover: unit, data validation, integration, API, frontend component, browser E2E, and the AI eval harness. See `docs/TEST_STRATEGY.md`.
- Run the tests after each component. **Never claim tests pass without running them**, and report the real output, including failures.
- Always include the injected-failure path and the 409 invalid-transition case.

## Development constraints

- Work **incrementally, one component at a time**. Stop for review after each step. Do not generate the whole app at once.
- **Do not overengineer.** No auth, real sending, streaming, job queues, multi-user, vector DBs or extra features beyond the agreed scope.
- **Do not invent features** and do not describe planned work as done.
- Every design decision must be explainable by the candidate in an interview. Prefer boring and obvious.
- Update `docs/AI_INTERACTION_LOG.md` as work progresses. Record real interactions only, including what was accepted, changed or rejected.
- Keep docs concise; update them when the design changes.

## Scope cut order (if time runs short)

Second E2E test, then edit-before-approve, then markdown eval report, then live-eval workflow.
Never cut: the injected failure, the 409 state test, the eval pass threshold, the interaction log.
