.PHONY: test lint typecheck format install dev clean

# Run unit tests (parallel, skip integration)
test:
	python -m pytest tests/ -q -n auto -m "not integration" --tb=short

# Run a specific test file
test-file:
	python -m pytest $(FILE) -x -q -o "addopts=" --tb=short

# Lint with ruff
lint:
	python -m ruff check .

# Type checking (incremental — start with core modules)
typecheck:
	python -m mypy agent/ gateway/config.py gateway/rate_limiter.py gateway/health.py gateway/shutdown.py hermes_state.py --ignore-missing-imports

# Format with ruff
format:
	python -m ruff format .

# Install all dependencies including dev
install:
	pip install -e ".[all,dev]"

# Install dev dependencies only
dev:
	pip install -e ".[dev]"

# Run production hardening tests only
test-hardening:
	python -m pytest tests/test_shell_injection.py tests/test_production_hardening.py -x -q -o "addopts=" --tb=short

# Clean build artifacts
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .mypy_cache .pytest_cache build dist *.egg-info
