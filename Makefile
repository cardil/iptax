# Makefile for iptax
# Using guard files for idempotent operations

.PHONY: help
help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# Guard files directory
GUARDS := .make

# Python and pip
PYTHON := python3
PIP := $(PYTHON) -m pip

# Virtual environment
VENV := .venv
VENV_BIN := $(VENV)/bin
VENV_PYTHON := $(VENV_BIN)/python
VENV_PIP := $(VENV_PYTHON) -m pip

# Source tracking
SRC_FILES := $(shell find src -type f -name '*.py' 2>/dev/null)
TEST_FILES := $(shell find tests -type f -name '*.py' 2>/dev/null)

##@ Installation

$(VENV): $(GUARDS)/venv.done
$(GUARDS)/venv.done: pyproject.toml
	@mkdir -p $(GUARDS)
	$(PYTHON) -m venv $(VENV)
	$(VENV_PIP) install --upgrade pip setuptools wheel
	@touch $@

.PHONY: install
install: $(GUARDS)/install.done  ## Install dependencies (idempotent)

$(GUARDS)/install.done: $(GUARDS)/venv.done pyproject.toml
	@mkdir -p $(GUARDS)
	$(VENV_PIP) install -e ".[dev]"
	$(VENV_PYTHON) -m playwright install chromium
	@touch $@

##@ Testing

.PHONY: test
test: unit e2e  ## Run all tests

.PHONY: unit
unit: $(GUARDS)/unit.passed  ## Run unit tests

$(GUARDS)/unit.passed: $(GUARDS)/install.done $(SRC_FILES) $(TEST_FILES)
	@mkdir -p $(GUARDS)
	$(VENV_BIN)/pytest tests/unit/ -v
	@touch $@

.PHONY: e2e
e2e: $(GUARDS)/e2e.passed  ## Run end-to-end tests

$(GUARDS)/e2e.passed: $(GUARDS)/install.done $(GUARDS)/unit.passed $(SRC_FILES) $(TEST_FILES)
	@mkdir -p $(GUARDS)
	$(VENV_BIN)/pytest tests/e2e/ -v
	@touch $@

.PHONY: test-watch
test-watch: $(GUARDS)/install.done  ## Run tests in watch mode
	$(VENV_BIN)/pytest-watch

##@ Code Quality

.PHONY: lint
lint: $(GUARDS)/lint.passed  ## Run linter (idempotent)

$(GUARDS)/lint.passed: $(GUARDS)/install.done $(SRC_FILES)
	@mkdir -p $(GUARDS)
	$(VENV_BIN)/ruff check src/ tests/
	@touch $@

.PHONY: format
format: $(GUARDS)/format.done  ## Format code (idempotent)

$(GUARDS)/format.done: $(GUARDS)/install.done $(SRC_FILES) $(TEST_FILES)
	@mkdir -p $(GUARDS)
	$(VENV_BIN)/black src/ tests/
	$(VENV_BIN)/ruff check --fix src/ tests/
	@touch $@

.PHONY: format-check
format-check: $(GUARDS)/install.done  ## Check if code formatting is correct
	$(VENV_BIN)/black src/ tests/
	$(VENV_BIN)/ruff check --fix src/ tests/
	@if ! git diff --exit-code > /dev/null 2>&1; then \
		echo "Error: Code formatting changes detected. Please run 'make format' and commit the changes."; \
		git diff; \
		exit 1; \
	fi
	@echo "✓ Code formatting is correct"

.PHONY: typecheck
typecheck: $(GUARDS)/typecheck.passed  ## Run type checker

$(GUARDS)/typecheck.passed: $(GUARDS)/install.done $(SRC_FILES)
	@mkdir -p $(GUARDS)
	$(VENV_BIN)/mypy src/
	@touch $@

.PHONY: check
check: lint format-check typecheck  ## Run all code quality checks (lint + format + typecheck)
	@echo "✓ All code quality checks passed"

##@ Verification

.PHONY: verify
verify: $(GUARDS)/lint.passed $(GUARDS)/format.done test  ## Run full verification (lint + format + tests)
	@echo "✓ All verifications passed"

##@ Development

.PHONY: clean
clean:  ## Clean build artifacts and caches
	rm -rf $(GUARDS)/
	rm -rf .pytest_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf dist/
	rm -rf build/
	rm -rf *.egg-info/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
	find . -type f -name '*.pyo' -delete

.PHONY: distclean
distclean: clean  ## Complete cleanup including venv
	rm -rf $(VENV)

.PHONY: coverage
coverage: $(GUARDS)/install.done  ## Run tests with coverage report
	$(VENV_BIN)/pytest --cov=iptax --cov-report=html --cov-report=term
	@echo "Coverage report: htmlcov/index.html"

##@ Utilities

.PHONY: shell
shell: $(GUARDS)/install.done  ## Start interactive Python shell
	$(VENV_BIN)/python

.PHONY: run
run: $(GUARDS)/install.done  ## Run the CLI tool
	$(VENV_BIN)/iptax

.PHONY: config
config: $(GUARDS)/install.done  ## Run configuration wizard
	$(VENV_BIN)/iptax config

.PHONY: report
report: $(GUARDS)/install.done  ## Generate report for current month
	$(VENV_BIN)/iptax report