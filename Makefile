.PHONY: check dev migrate stage types backend-check frontend-check

BACKEND := backend
FRONTEND := frontend
PY := $(BACKEND)/.venv/bin/python

check: backend-check frontend-check

backend-check:
	cd $(BACKEND) && .venv/bin/ruff check .
	cd $(BACKEND) && .venv/bin/mypy app
	cd $(BACKEND) && .venv/bin/pytest

frontend-check:
	cd $(FRONTEND) && npm run lint
	cd $(FRONTEND) && npm run typecheck

dev:
	trap 'kill 0' EXIT; \
	(cd $(BACKEND) && .venv/bin/uvicorn app.main:app --reload --port 8000) & \
	(cd $(BACKEND) && .venv/bin/python -m app.worker) & \
	(cd $(FRONTEND) && npm run dev) & \
	wait

migrate:
	cd $(BACKEND) && .venv/bin/python -m app.db.migrate

# 사용: make stage S=collect F=cafe_20
stage:
	cd $(BACKEND) && .venv/bin/python -m app.worker.stage_runner --stage $(S) --fixture $(F)

types:
	cd $(FRONTEND) && npm run types
