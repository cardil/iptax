# Testing Strategy

This document describes the testing approach, tools, and strategies for the iptax tool.

**See also:**
- [Main Documentation](project.md) - Project overview and onboarding
- [Requirements](requirements.md) - Detailed requirements
- [Architecture](architecture.md) - Technical design
- [Workflows](workflows.md) - Detailed workflow steps
- [Implementation](implementation.md) - Development phases
- [Edge Cases](edge-cases.md) - Error handling scenarios
- [Examples](examples.md) - Configuration and usage examples

---

## Testing Approach

**Overall Philosophy:**
- Test-driven development where appropriate
- Focus on critical path and error handling
- Mock external dependencies (AI, Workday, did)
- Use fixtures for sample data
- Make-based orchestration with guard files for idempotent builds

---

## Make-Based Test Orchestration

### Primary Test Targets

See [`Makefile`](../Makefile:1) for complete configuration.

```makefile
# Key targets
.PHONY: init test unit e2e lint format typecheck verify clean coverage

init: $(GUARDS)/init.done   ## Initialize development environment
test: unit e2e              ## Run all tests
unit: $(GUARDS)/unit.passed ## Run unit tests
e2e: $(GUARDS)/e2e.passed   ## Run end-to-end tests
verify: lint format test    ## Run full verification
```

### Guard File System

**Purpose:** Enable idempotent builds - skip unnecessary work if nothing changed.

**How it works:**
```bash
# First run - executes
$ make init
pip install -e ".[dev]"
playwright install chromium
touch .make/init.done

# Second run (no changes) - skips
$ make init
make: '.make/init.done' is up to date.

# After pyproject.toml change - re-executes
$ touch pyproject.toml
$ make init
pip install -e ".[dev]"
touch .make/init.done
```

**Dependency Graph:**
```text
verify
├── lint → init
├── format → init
└── test
    ├── unit → init
    └── e2e → init + unit
```

### Common Make Commands

```bash
# Initialize development environment
make init

# Run only unit tests
make unit

# Run only e2e tests
make e2e

# Run linter
make lint

# Format code
make format

# Full verification (what CI runs)
make verify

# With coverage report
make coverage

# Clean and verify fresh
make clean verify
```

---

## Unit Tests

**Scope:** Test individual components in isolation

### Key Areas to Test

#### 1. Configuration Management ([`test_config.py`](../tests/unit/test_cli.py))
- Settings loading and validation
- Provider selection parsing
- Config file creation
- Validation error handling
- Default value handling

#### 2. History Tracking (`test_history.py`)
- Date range calculation
- History file creation and updates
- Cutoff date tracking
- Gap detection
- Regeneration scenarios

#### 3. did Integration (`test_did_integration.py`)
- SDK initialization
- Change extraction
- Repository parsing
- Error handling for auth failures
- Provider filtering

#### 4. AI Filtering (`test_ai_filter.py`)
- Batch prompt generation
- Response parsing (YAML/TOML)
- Judgment cache operations
- Decision logic (INCLUDE/EXCLUDE/UNCERTAIN/ERROR)
- User override handling

#### 5. Report Compiler (`test_report_compiler.py`)
- Markdown formatting
- Emoji removal
- Project extraction
- Data aggregation

#### 6. PDF Generator (`test_pdf_generator.py`)
- Template rendering
- Bilingual text handling
- PDF creation
- File output

### Example Test Cases

```python
# test_history.py
def test_first_report_prompts_for_cutoff():
    """First report should prompt for previous month cutoff."""
    history = HistoryManager()
    assert not history.has_previous_report()

def test_subsequent_report_uses_previous_cutoff():
    """Second report should use previous cutoff + 1 day."""
    history = HistoryManager()
    history.add_entry("2024-10", date(2024, 10, 25))
    start_date, _ = history.get_date_range("2024-11")
    assert start_date == date(2024, 10, 26)

# test_ai_filter.py
def test_cached_judgment_reused():
    """Cached judgments should be reused."""
    cache = {"owner/repo#123": {"decision": "INCLUDE"}}
    filter = AIFilter(cache=cache)
    decision = filter.judge_change("owner/repo#123", ...)
    assert decision == "INCLUDE"
    assert filter.api_calls == 0
```

---

## End-to-End Tests

**Scope:** Test complete workflows from start to finish

### Critical Paths

#### 1. First-Time Setup
- No config exists → interactive setup → report generation
- Validates: config created, reports generated, history updated

#### 2. Regular Monthly Report
- Config exists → fetch changes → AI filter → generate reports
- Validates: correct date range, reports created, history updated

#### 3. Regeneration Flow
- Report exists → confirm regeneration → overwrite files
- Validates: files updated, history regenerated_at set

### Example E2E Test

```python
# tests/e2e/test_full_workflow.py
import pytest
from click.testing import CliRunner
from iptax.cli import cli

@pytest.fixture
def mock_environment(tmp_path, monkeypatch):
    """Setup complete test environment"""
    config_dir = tmp_path / ".config" / "iptax"
    cache_dir = tmp_path / ".cache" / "iptax"
    config_dir.mkdir(parents=True)
    cache_dir.mkdir(parents=True)
    
    monkeypatch.setenv("HOME", str(tmp_path))
    
    # Create did config
    did_config = tmp_path / ".did" / "config"
    did_config.parent.mkdir()
    did_config.write_text("""
    [github]
    type = github
    url = https://github.com
    """)
    
    return {
        "config_dir": config_dir,
        "cache_dir": cache_dir,
        "did_config": did_config
    }

def test_complete_report_generation(mock_environment, mock_did, mock_ai):
    """Test complete workflow from config to report generation"""
    runner = CliRunner()
    
    # Step 1: Configure
    config_result = runner.invoke(cli, ['config'], input="""
    Krzysztof Suszyński
    Vaclav Tunka
    Red Hat OpenShift Serverless
    80
    y
    gemini
    test-api-key
    n
    """)
    assert config_result.exit_code == 0
    
    # Step 2: Generate report
    mock_did.return_value.get_changes.return_value = [
        MockChange(
            title="Add feature",
            repo="test/repo",
            url="https://github.com/test/repo/pull/1"
        )
    ]
    
    mock_ai.return_value = """
    judgments:
      - change_url: "https://github.com/test/repo/pull/1"
        decision: "INCLUDE"
        rationale: "Product feature"
    """
    
    report_result = runner.invoke(
        cli, 
        ['report', '--month', '2024-11'],
        input='160\n'  # Manual hours
    )
    
    assert report_result.exit_code == 0
    assert "Report generated successfully" in report_result.output
    
    # Verify outputs exist
    output_dir = mock_environment["config_dir"] / "output"
    assert (output_dir / "2024-11 IP TAX Report.md").exists()
    assert (output_dir / "2024-11 IP TAX Work Card.pdf").exists()
    assert (output_dir / "2024-11 IP TAX Raport.pdf").exists()
```

---

## Test Fixtures

**Location:** `tests/fixtures/`

```text
tests/fixtures/
├── sample_did_output.py       # Mock did SDK responses
├── sample_config.yaml          # Valid configuration
├── sample_history.toml         # History with multiple months
└── sample_ai_cache.json        # Pre-filled AI judgment cache
```

---

## Test Execution

### Using Make (Recommended)

```bash
# Full verification (what CI runs)
make verify

# Initialize development environment
make init

# Run only unit tests
make unit

# Run only e2e tests
make e2e

# Run linter
make lint

# Format code
make format

# With coverage report
make coverage

# Clean and verify fresh
make clean verify
```

### Using pytest Directly

```bash
# Run all tests
pytest

# Run only unit tests
pytest tests/unit/

# Run only e2e tests
pytest tests/e2e/

# Run specific test file
pytest tests/unit/test_config.py

# Run with coverage
pytest --cov=iptax --cov-report=html

# Run verbose
pytest -v

# Run with markers
pytest -m "not slow"
```

---

## Test Coverage

**Target Metrics:**
- Unit test coverage: >80% for core logic
- Integration test coverage: >60%
- All critical paths tested (e2e)
- All error conditions tested

**Coverage Configuration:**

See [`pyproject.toml`](../pyproject.toml:183):
```toml
[tool.coverage.run]
source = ["src"]
omit = [
    "*/tests/*",
    "*/test_*.py",
    "*/__pycache__/*",
]

[tool.coverage.report]
precision = 2
show_missing = true
skip_covered = false
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "if TYPE_CHECKING:",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
]
```

---

## Mocking Strategy

### External Dependencies to Mock

1. **did SDK:** Mock PR/MR fetching
2. **AI Provider (LiteLLM):** Mock API calls and responses
3. **Workday (Playwright):** Mock browser automation
4. **File System:** Use temporary directories (pytest tmp_path)
5. **Network Calls:** Mock HTTP requests

### Example Mocks

```python
# Mock did SDK
@pytest.fixture
def mock_did_client(mocker):
    mock = mocker.patch('iptax.did_integration.Did')
    mock.return_value.get_changes.return_value = [
        MockChange(title="Test PR", repo="test/repo", number=1)
    ]
    return mock

# Mock AI provider
@pytest.fixture
def mock_ai_provider(mocker):
    mock = mocker.patch('litellm.completion')
    mock.return_value.choices[0].message.content = """
    judgments:
      - decision: INCLUDE
        reasoning: test
    """
    return mock

# Mock Playwright
@pytest.fixture
def mock_playwright(mocker):
    mock = mocker.patch('playwright.sync_api.sync_playwright')
    # Configure mock browser, page, etc.
    return mock
```

---

## Continuous Integration

**What CI Should Run:**

```yaml
# .github/workflows/test.yml example
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Initialize development environment
        run: make init
      - name: Run verification
        run: make verify
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

**CI Success Criteria:**
- All tests pass
- Linting passes
- Type checking passes
- Code formatting is correct
- Test coverage meets minimum threshold

---

## Test Quality Checklist

Before merging:
- [ ] All tests pass locally (`make verify`)
- [ ] New features have unit tests
- [ ] Critical paths have e2e tests
- [ ] Error conditions are tested
- [ ] Mocks are properly configured
- [ ] Tests are deterministic (no flaky tests)
- [ ] Test names clearly describe what is tested
- [ ] Coverage meets minimum threshold