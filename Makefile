.PHONY: frontend-install backend-install frontend-dev backend-dev frontend-build frontend-typecheck frontend-lint backend-test backend-lint ml-test validate

frontend-install:
	npm --prefix frontend install

backend-install:
	python -m pip install -r backend/requirements.txt
	python -m pip install -e ml

frontend-dev:
	npm --prefix frontend run dev

backend-dev:
	cd backend && python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

frontend-build:
	npm --prefix frontend run build

frontend-typecheck:
	npm --prefix frontend run typecheck

frontend-lint:
	npm --prefix frontend run lint

backend-test:
	cd backend && python -m pytest

backend-lint:
	python -m ruff check backend ml

ml-test:
	python -m pytest ml/tests

validate: frontend-typecheck frontend-lint frontend-build backend-lint backend-test ml-test

