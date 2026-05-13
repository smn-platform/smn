.PHONY: install dev test lint serve clean build docker

install:
	pip install -e .

dev:
	pip install -e ".[dev]"

test:
	python -m pytest tests/ -q

test-all:
	python -m pytest tests/ -q
	python -m pytest sdks/python/tests/ -q
	cd sdks/typescript && npx vitest run

lint:
	ruff check src/ tests/
	ruff format --check src/ tests/

format:
	ruff format src/ tests/

serve:
	smn serve --reload

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf dist/ build/ *.egg-info .pytest_cache .ruff_cache

build:
	python -m build

docker:
	docker compose up --build

docker-down:
	docker compose down -v
