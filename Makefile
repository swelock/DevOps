PYTHON ?= python3
VENV = .venv/bin/python

.PHONY: setup run test quality format deploy-check verify
setup:
	$(PYTHON) -m venv .venv
	$(VENV) -m pip install -r requirements-dev.txt
run:
	$(VENV) run.py
test:
	$(VENV) -m pytest -q
quality:
	$(VENV) -m ruff check .
	$(VENV) -m ruff format --check .
format:
	$(VENV) -m ruff format .
deploy-check:
	bash -n deploy/scripts/*.sh
	! rg -n 'DATABASE_PASSWORD=[^$$<[:space:]]' --glob '*.sh' --glob '*.env*' --glob '*.service' deploy .env.example
	! rg -n 'postgres(ql)?://[^:[:space:]]+:[^@[:space:]]+@' --glob '!*.md' --glob '!*.example' .
verify: quality test deploy-check
	git diff --check
