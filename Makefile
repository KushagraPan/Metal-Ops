# MetalOps Lite developer commands.
# Windows uses .venv/Scripts/python.exe and npm.cmd; other platforms use bin/python and npm.

ifeq ($(OS),Windows_NT)
PYTHON ?= python
VENV_PY := .venv/Scripts/python.exe
NPM ?= npm.cmd
else
PYTHON ?= python3
VENV_PY := .venv/bin/python
NPM ?= npm
endif

.DEFAULT_GOAL := help

.PHONY: help install dev test test-unit test-integration test-db-up test-db-down typecheck clean migrate seed reset-db stack-up stack-down stack-test stack-persistence rollback-test

help:
	@echo make dev               API on http://127.0.0.1:8000 and frontend on http://127.0.0.1:5173
	@echo make test              unit + integration tests, Vitest and TypeScript check
	@echo make test-unit         pytest unit tests only
	@echo make test-integration  pytest integration tests only
	@echo make test-db-up        start PostgreSQL test container
	@echo make test-db-down      stop and remove PostgreSQL test container
	@echo make stack-up          start Docker Compose stack with test port published
	@echo make stack-down        stop and tear down Docker Compose stack
	@echo make stack-test        run integration tests against Compose stack
	@echo make stack-persistence verify report persistence across stack restart
	@echo make rollback-test     verify deployment and rollback using image tags
	@echo make install           create the virtualenv and install dependencies
	@echo make migrate           apply Alembic migrations to DATABASE_URL
	@echo make seed              migrate, then insert the fictional demo data
	@echo make reset-db          delete the local dev database, migrate and reseed

install: .venv/.installed frontend/node_modules/.installed

.venv/.installed: requirements.txt
	$(PYTHON) -m venv .venv
	$(VENV_PY) -m pip install --upgrade pip
	$(VENV_PY) -m pip install -r requirements.txt
	$(VENV_PY) -c "from pathlib import Path; Path('.venv/.installed').touch()"

frontend/node_modules/.installed: frontend/package.json
	cd frontend && $(NPM) install
	$(PYTHON) -c "from pathlib import Path; Path('frontend/node_modules/.installed').touch()"

migrate: install
	$(VENV_PY) -m alembic upgrade head

seed: migrate
	$(VENV_PY) -m app.seed

reset-db: install
	$(VENV_PY) scripts/reset_db.py
	$(MAKE) seed

dev: install
	$(VENV_PY) scripts/dev.py

test-db-up: install
	$(VENV_PY) scripts/test_db.py up

test-db-down: install
	$(VENV_PY) scripts/test_db.py down

stack-up: install
	docker compose -f compose.yaml -f compose.test.yaml up -d --build --wait

stack-down: install
	docker compose -f compose.yaml -f compose.test.yaml down

stack-test: install
	$(VENV_PY) scripts/run_stack_test.py

stack-persistence: install
	$(VENV_PY) scripts/stack_persistence_test.py

rollback-test: install
	$(VENV_PY) scripts/rollback_test.py

test-unit: install
	$(VENV_PY) -m pytest tests/unit

test-integration: install
	$(VENV_PY) scripts/test_db.py check
	$(VENV_PY) -m pytest tests/integration

test: install
	$(VENV_PY) scripts/test_db.py check
	$(VENV_PY) -m pytest
	cd frontend && $(NPM) run test
	cd frontend && $(NPM) run typecheck

typecheck: install
	cd frontend && $(NPM) run typecheck

clean:
	$(PYTHON) -c "import shutil; [shutil.rmtree(p, ignore_errors=True) for p in ('.venv', 'frontend/node_modules')]"
