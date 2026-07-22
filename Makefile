.PHONY: frontend-install backend-install frontend-dev backend-dev frontend-build frontend-typecheck frontend-lint frontend-test backend-test backend-lint backend-format ml-test data-credentials data-smoke data-hackathon data-full validate

frontend-install:
	npm --prefix frontend install

backend-install:
	python -m pip install -r backend/requirements.txt
	python -m pip install -e ml

frontend-dev:
	npm --prefix frontend run dev

backend-dev:
	python -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000

frontend-build:
	npm --prefix frontend run build

frontend-typecheck:
	npm --prefix frontend run typecheck

frontend-lint:
	npm --prefix frontend run lint

frontend-test:
	npm --prefix frontend run test

backend-test:
	python -m pytest backend/tests

backend-lint:
	python -m ruff check backend ml

backend-format:
	python -m ruff format --check backend ml

ml-test:
	python -m pytest ml/tests

data-credentials:
	python -m airview_ml.data.pipeline credentials

data-smoke:
	python -m airview_ml.data.pipeline fetch --profile smoke

data-hackathon:
	python -m airview_ml.data.pipeline fetch --profile hackathon

data-full:
	python -m airview_ml.data.pipeline fetch --profile full-india

validate: frontend-typecheck frontend-lint frontend-test frontend-build backend-lint backend-format backend-test ml-test
