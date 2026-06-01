SHELL := /bin/bash

.PHONY: help
help:
	@echo "Targets:"
	@echo "  dev-up          Start local dependency stack (db, redis, minio, qdrant, langfuse)"
	@echo "  dev-down        Stop local dependencies"
	@echo "  backend-setup   Install backend runtime dependencies (from backend/)"
	@echo "  backend-run     Run backend (from backend/)"
	@echo "  paper-runtime-init  Warm paper-review runtime models and tools (from backend/)"
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
	cd backend && python3 main.py

.PHONY: backend-setup
backend-setup:
	cd backend && python3 -m pip install -r requirements.txt

.PHONY: paper-runtime-init
paper-runtime-init:
	cd backend && PYTHONPATH=. python3 scripts/init_paper_review_runtime.py

.PHONY: frontend-dev
frontend-dev:
	cd frontend && npm install && npm run dev

.PHONY: db-migrate
db-migrate:
	cd backend && PYTHONPATH=. alembic upgrade head
