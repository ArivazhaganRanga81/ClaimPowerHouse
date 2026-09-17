.PHONY: init test lint api web-build extension-build

init:
	python -m app.cli init

test:
	python -m pytest

lint:
	python -m ruff check apps/api

api:
	python -m uvicorn app.main:app --app-dir apps/api --reload

web-build:
	cd apps/web && npm run build

extension-build:
	cd apps/vscode-extension && npm run compile

