.PHONY: install install-backend install-frontend backend frontend test test-backend test-frontend lint build eval

BACKEND_PY = backend/.venv/bin

install: install-backend install-frontend

install-backend:
	python3.12 -m venv backend/.venv
	$(BACKEND_PY)/pip install -r backend/requirements-dev.txt

install-frontend:
	cd frontend && npm install

backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

test: test-backend test-frontend

test-backend:
	cd backend && .venv/bin/pytest

test-frontend:
	cd frontend && npm test

eval:
	cd backend && .venv/bin/python -m evals.run

lint:
	cd backend && .venv/bin/ruff check .
	cd frontend && npm run typecheck

build:
	cd frontend && npm run build
