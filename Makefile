install:
	pip install -e ".[dev]"

migrate:
	alembic upgrade head

seed:
	alembic upgrade head

run:
	python -m app.main

test:
	pytest -q

lint:
	ruff check src tests

format:
	ruff format src tests
