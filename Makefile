.PHONY: install lint format test run

install:
	pip install -r requirements.txt

lint:
	ruff check .
	black --check .

format:
	ruff check --fix .
	black .

test:
	pytest -q

run:
	python run_pipeline.py
