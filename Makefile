.PHONY: install run test lint

install:
	python -m pip install -e '.[dev]'

run:
	uvicorn app.main:app --reload

test:
	pytest -q

lint:
	ruff check .
