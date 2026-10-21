PYTHON ?= python3
VENV ?= .venv
BIN := $(VENV)/bin
ENV ?= dev

.PHONY: help venv install run-api test lint format openapi

help:
	@echo "targets: venv install run-api test lint format openapi"
	@echo "ENV=dev|prod (default: dev -> .env.dev)"
	@echo "Always uses .venv/bin/python (not system python)"

venv:
	$(PYTHON) -m venv $(VENV)

install: venv
	$(BIN)/pip install -U pip
	$(BIN)/pip install -r requirements-dev.txt

run-api:
	$(BIN)/python scripts/run.py --env $(ENV)

test:
	$(BIN)/pytest -q

lint:
	$(BIN)/ruff check app tests scripts
	$(BIN)/ruff format --check app tests scripts

format:
	$(BIN)/ruff check --fix app tests scripts
	$(BIN)/ruff format app tests scripts

openapi:
	$(BIN)/python scripts/export_openapi.py
