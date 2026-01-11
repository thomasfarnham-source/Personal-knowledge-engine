# Makefile — Automates local development tasks like formatting, linting, type checking, and testing

# Declare these targets as phony (not actual files)
.PHONY: check lint format test type fix

# Auto-fix formatting issues using black and isort
fix:
	black .
	isort .

# Run all checks in sequence: format, lint, type check, and tests
check: format lint type test

# Format all Python files using black
format:
	black .

# Lint code using flake8 to catch style issues and simple bugs
lint:
	flake8

# Run static type checks using mypy
type:
	mypy .

# Run unit tests using pytest in quiet mode
test:
	pytest -q