PYTHON ?= python3
VENV = .venv/bin/python

.PHONY: setup run test quality format verify
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
verify: quality test
	git diff --check
