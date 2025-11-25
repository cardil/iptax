# Makefile for iptax
# Using guard files for idempotent operations

# Colors
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[0;33m
BLUE := \033[0;34m
CYAN := \033[0;36m
RESET := \033[0m

# Emojis
CHECK := ✅
CROSS := ❌
ROCKET := 🚀
GEAR := "⚙️ "
TEST := 🧪
CLEAN := 🧹
BOOK := 📚

.PHONY: help
help:  ## Show this help
	@echo -e "$(CYAN)$(BOOK) Available targets:$(RESET)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[0;36m%-20s\033[0m %s\n", $$1, $$2}'


# Python and pip
PYTHON := python3
PIP := $(PYTHON) -m pip

# Virtual environment
VENV := .venv
GUARDS := $(VENV)/.make
VENV_BIN := $(VENV)/bin
VENV_PYTHON := $(VENV_BIN)/python
VENV_PIP := $(VENV_PYTHON) -m pip

# Source tracking
SRC_FILES := $(shell find src -type f -name '*.py' 2>/dev/null)
TEST_FILES := $(shell find tests scripts -type f -name '*.py' 2>/dev/null) Makefile
MD_FILES := $(shell find docs -type f -name '*.md' 2>/dev/null) README.md

##@ Installation

.PHONY: install
install:  ## Install iptax to system or user environment
	@echo -e "$(BLUE)$(GEAR) Installing iptax...$(RESET)"
	@if [ -w /usr/local ]; then \
		echo -e "$(GREEN)Installing to system location (/usr/local)...$(RESET)"; \
		$(PIP) install .; \
	else \
		echo -e "$(YELLOW)No root permissions, installing to user location" \
			"(~/.local)...$(RESET)"; \
		$(PIP) install --user .; \
	fi
	@echo -e "$(GREEN)$(CHECK) iptax installed successfully$(RESET)"
	@echo -e "$(CYAN)Run 'iptax --help' to get started$(RESET)"

##@ Development Setup

$(VENV): $(VENV)/venv.done
$(VENV)/venv.done: pyproject.toml
	@mkdir -p $(GUARDS)
	$(PYTHON) -m venv $(VENV)
	$(VENV_PIP) install --upgrade pip setuptools wheel
	@touch $@

.PHONY: init
init: $(VENV)/init.done  ## Initialize development environment (install deps)

$(VENV)/init.done: $(VENV)/venv.done pyproject.toml
	@mkdir -p $(GUARDS)
	$(VENV_PIP) install -e ".[dev]"
	$(VENV_PYTHON) -m playwright install chromium
	@touch $@

##@ Testing

.PHONY: test
test: unit e2e  ## Run all tests

.PHONY: unit
unit: $(GUARDS)/unit.passed  ## Run unit tests
	@echo -e "$(TEST) Unit tests ........................... $(GREEN)PASSED$(RESET)"

$(GUARDS)/unit.passed: $(VENV)/init.done $(SRC_FILES) $(TEST_FILES)
	@mkdir -p $(GUARDS)
	$(VENV_BIN)/pytest tests/unit/ -v
	@touch $@

.PHONY: e2e
e2e: $(GUARDS)/e2e.passed  ## Run end-to-end tests
	@echo -e "$(GEAR) E2E tests ............................ $(GREEN)PASSED$(RESET)"

$(GUARDS)/e2e.passed: $(VENV)/init.done $(GUARDS)/unit.passed \
	$(SRC_FILES) $(TEST_FILES)
	@mkdir -p $(GUARDS)
	$(VENV_BIN)/pytest tests/e2e/ -v --no-cov
	@touch $@

.PHONY: test-watch
test-watch: $(VENV)/init.done  ## Run tests in watch mode
	$(VENV_BIN)/pytest-watch tests/unit/

##@ Code Quality

.PHONY: lint
lint: $(GUARDS)/lint.passed  ## Run linter (idempotent)

$(GUARDS)/lint.passed: $(VENV)/init.done $(SRC_FILES) $(TEST_FILES) \
	$(MD_FILES) pyproject.toml .editorconfig
	@mkdir -p $(GUARDS)
	$(VENV_BIN)/ruff check src/ tests/
	$(VENV_BIN)/ec
	@touch $@

.PHONY: format
format: $(VENV)/init.done  ## Format code and markdown
	$(VENV_BIN)/black src/ tests/
	$(VENV_BIN)/ruff check --fix src/ tests/
	$(VENV_BIN)/mdformat --wrap 88 docs/ README.md
	$(VENV_PYTHON) scripts/fix_whitespace.py
	@echo -e "$(GREEN)$(CHECK) Code and markdown formatted$(RESET)"

.PHONY: format-check
format-check: $(GUARDS)/format.done  ## Check if code formatting is correct
	@echo -e "$(BOOK) Code formatting  ..................... $(GREEN)CORRECT$(RESET)"

$(GUARDS)/format.done: $(VENV)/init.done $(SRC_FILES) $(TEST_FILES) \
	$(MD_FILES) pyproject.toml .editorconfig
	@mkdir -p $(GUARDS)
	@echo -e "$(BLUE)$(GEAR) Checking code formatting...$(RESET)"
	@$(VENV_BIN)/black --check --diff src/ tests/
	@$(VENV_BIN)/ruff check src/ tests/
	@$(VENV_BIN)/mdformat --wrap 88 --check docs/ README.md
	@touch $@

.PHONY: typecheck
typecheck: $(GUARDS)/typecheck.passed  ## Run type checker

$(GUARDS)/typecheck.passed: $(VENV)/init.done $(SRC_FILES) pyproject.toml
	@mkdir -p $(GUARDS)
	$(VENV_BIN)/mypy src/
	@touch $@

.PHONY: check
check: lint format-check typecheck  ## Run all code quality checks
	@echo -e "$(CHECK) Code quality ......................... $(GREEN)PASSED$(RESET)"

##@ Verification

.PHONY: verify
verify: check test  ## Full verification

##@ Development

.PHONY: clean
clean:  ## Clean build artifacts and caches
	@echo -e "$(YELLOW)$(CLEAN) Cleaning build artifacts...$(RESET)"
	@rm -rf $(GUARDS)/
	@rm -rf .pytest_cache/
	@rm -rf htmlcov/
	@rm -rf .coverage coverage.xml
	@rm -rf dist/
	@rm -rf build/
	@rm -rf *.egg-info/
	@rm -rf .mypy_cache/
	@rm -rf .ruff_cache/
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name '*.pyc' -delete
	@find . -type f -name '*.pyo' -delete
	@echo -e "$(GREEN)$(CHECK) Build artifacts cleaned$(RESET)"

.PHONY: distclean
distclean: clean  ## Complete cleanup including venv
	@echo -e "$(YELLOW)$(CLEAN) Removing virtual environment...$(RESET)"
	@rm -rf $(VENV)
	@echo -e "$(GREEN)$(CHECK) Complete cleanup done$(RESET)"


##@ Utilities

.PHONY: shell
shell: $(VENV)/init.done  ## Start interactive Python shell
	$(VENV_BIN)/python
