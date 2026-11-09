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

.PHONY: help install dev test typecheck clean migrate seed

help:
	@echo make dev        API on http://127.0.0.1:8000 and frontend on http://127.0.0.1:5173
	@echo make test       pytest, Vitest and the TypeScript check
	@echo make install    create the virtualenv and install dependencies
	@echo make migrate    apply Alembic migrations to DATABASE_URL
	@echo make seed       migrate, then insert the fictional demo data

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

dev: install
	$(VENV_PY) scripts/dev.py

test: install
	$(VENV_PY) -m pytest
	cd frontend && $(NPM) run test
	cd frontend && $(NPM) run typecheck

typecheck: install
	cd frontend && $(NPM) run typecheck

clean:
	$(PYTHON) -c "import shutil; [shutil.rmtree(p, ignore_errors=True) for p in ('.venv', 'frontend/node_modules')]"
