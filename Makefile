SHELL := /bin/bash

.PHONY: help
help:
	@echo "Targets:"
	@echo "  dev-up          Start local dependencies (docker compose)"
	@echo "  dev-down        Stop local dependencies"
	@echo "  backend-run     Run backend (from backend/)"
	@echo "  frontend-dev    Run frontend dev server (from frontend/)"
	@echo "  db-migrate      Run Alembic migrations (from backend/)"

.PHONY: dev-up
dev-up:
	docker compose up -d

.PHONY: dev-down
dev-down:
	docker compose down

.PHONY: backend-run
backend-run:
	cd backend && python main.py

.PHONY: frontend-dev
frontend-dev:
	cd frontend && npm install && npm run dev

.PHONY: db-migrate
db-migrate:
	cd backend && PYTHONPATH=. alembic upgrade head
