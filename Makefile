PYTHON ?= python3
VENV = .venv/bin/python
FILE ?=

.PHONY: setup run test test-raw quality format migrate backup restore mutation-check deploy-check verify up down container-check postgres-check
setup:
	$(PYTHON) -m venv .venv
	$(VENV) -m pip install -r requirements-dev.txt
	$(VENV) -m scripts.manage setup
run:
	$(VENV) run.py
test:
	mkdir -p reports
	$(VENV) -m pytest -q --explain --junitxml=reports/tests.xml --cov=campus --cov-branch --cov-report=term-missing --cov-report=xml:reports/coverage.xml --cov-report=html:reports/htmlcov --cov-fail-under=80
test-raw:
	$(VENV) -m pytest -v
quality:
	mkdir -p reports
	$(VENV) -m ruff check .
	$(VENV) -m ruff format --check .
	$(VENV) -m bandit -r campus scripts migrations run.py -f json -o reports/bandit.json
format:
	$(VENV) -m ruff format .
migrate:
	$(VENV) -m scripts.manage migrate
backup:
	$(VENV) -m scripts.manage backup $(if $(FILE),--file "$(FILE)",)
restore:
	$(VENV) -m scripts.manage restore $(if $(FILE),--file "$(FILE)",)
mutation-check:
	$(VENV) -m scripts.check_mutations
postgres-check:
	$(VENV) -m scripts.check_postgres
deploy-check:
	bash -n deploy/scripts/*.sh
	! rg -n 'DATABASE_PASSWORD=[^$$<[:space:]]' --glob '*.sh' --glob '*.env*' --glob '*.service' deploy .env.example
	! rg -n 'postgres(ql)?://[^:[:space:]]+:[^@[:space:]]+@' --glob '!*.md' --glob '!*.example' .
verify:
	$(MAKE) quality
	$(MAKE) test
	$(MAKE) mutation-check
	$(MAKE) deploy-check
	git diff --check
up:
	docker compose up --build -d --wait
down:
	docker compose down
container-check:
	docker compose config --quiet
	docker compose exec -T app python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=5)'
