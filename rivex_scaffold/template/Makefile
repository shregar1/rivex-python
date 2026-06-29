.PHONY: install dev run test lint typecheck ci env

PYTHON ?= python3
PROJECT_SLUG := {{project_slug}}
PROJECT_NAME := {{project_name}}

env:
	@if [ ! -f .env ]; then cp .env.example .env && echo "Created .env from .env.example"; else echo ".env already exists"; fi

install: env
	pip install -e ".[dev]"

dev:
	PYTHONPATH=. $(PYTHON) main.py

run:
	PYTHONPATH=. $(PYTHON) main.py

test:
	pytest tests -q

lint:
	ruff check .

typecheck:
	$(PYTHON) -m compileall -q abstractions controllers services repositories dtos utilities constants configurations errors

ci: lint typecheck test
