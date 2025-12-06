# Architecture & Design

This document describes the technical architecture and design decisions for the iptax
tool.

**See also:**

- [Main Documentation](project.md) - Project overview and onboarding
- [Requirements](requirements.md) - Detailed requirements
- [Workflows](workflows.md) - Detailed workflow steps
- [Testing](testing.md) - Testing strategy
- [Implementation](implementation.md) - Development phases
- [Edge Cases](edge-cases.md) - Error handling scenarios
- [Examples](examples.md) - Configuration and usage examples

______________________________________________________________________

## Technical Architecture

### Technology Stack

**Language:** Python 3.11+

**Rationale:**

- Native integration with psss/did (Python project)
- Rich ecosystem for CLI, PDF generation, browser automation, AI providers
- Excellent type hints support for maintainability
- Cross-platform compatibility

### Core Dependencies

See [`pyproject.toml`](../pyproject.toml:1) for the complete dependency list.

**Key Dependencies:**

- **CLI Framework:** `click>=8.1.7`
- **Terminal UI:** `rich>=13.7.0`, `questionary>=2.0.1`
- **Configuration:** `pyyaml>=6.0.1`, `pydantic>=2.5.0`
- **AI Provider:** `litellm>=1.44.0`, `google-generativeai>=0.3.0`
- **Browser Automation:** `playwright>=1.40.0`
- **PDF Generation:** `weasyprint>=60.0`, `jinja2>=3.1.2`
- **HTTP Client:** `httpx>=0.25.0`
- **Date/Time:** `python-dateutil>=2.8.2`
- **Markdown:** `markdown>=3.5.0`
- **did Integration:** `did @ git+https://github.com/psss/did.git@refs/pull/311/head`

### Project Structure

```text
iptax-reporter/
├── src/
│   └── iptax/
│       ├── __init__.py
│       ├── cli.py              # CLI entry point, Click commands
│       ├── config/
│       │   ├── __init__.py     # Public config API
│       │   ├── base.py         # Configuration management, validation
│       │   └── interactive.py  # Interactive configuration wizard
│       ├── history.py          # History tracking, date range calculation
│       ├── did_integration.py  # psss/did SDK wrapper
│       ├── workday.py          # Workday client (Playwright automation)
│       ├── ai_filter.py        # AI filtering logic, cache management
│       ├── report_compiler.py  # Report data compilation
│       ├── pdf_generator.py    # PDF generation (WeasyPrint)
│       ├── tui.py              # TUI components for review
│       ├── models.py           # Pydantic data models
│       ├── exceptions.py       # Custom exceptions
│       └── templates/
│           ├── work_card.html      # Work Card PDF template
│           ├── tax_report.html     # Tax Report PDF template
│           └── styles.css          # Shared PDF styles
├── tests/
│   ├── unit/
│   ├── e2e/
│   └── fixtures/
├── docs/
│   ├── project.md              # Main entry point
│   ├── requirements.md         # Requirements
│   ├── architecture.md         # Technical design (this file)
│   ├── workflows.md            # Workflow steps
│   ├── testing.md              # Testing strategy
│   ├── implementation.md       # Development phases
│   ├── edge-cases.md           # Error handling
│   └── examples.md             # Configuration examples
├── pyproject.toml
├── README.md
├── LICENSE
└── .gitignore
```

### Key Design Decisions

#### 1. Click vs Typer for CLI

- **Choice:** Click
- **Rationale:** Mature, stable, excellent documentation, better pytest integration
- **Alternative:** Typer (newer, type-hint based, but less mature ecosystem)

#### 2. WeasyPrint vs ReportLab for PDFs

- **Choice:** WeasyPrint
- **Rationale:**
  - Pure Python (no external dependencies)
  - Excellent CSS support for layout
  - Can render HTML templates directly
  - Good Unicode/Polish character support
- **Alternative:** ReportLab (more control but harder complex layouts)

#### 3. Playwright vs Selenium for Browser Automation

- **Choice:** Playwright
- **Rationale:**
  - Modern, actively maintained
  - Better async support
  - Handles SAML/Kerberos flows well
  - Faster and more reliable
- **Alternative:** Selenium (older, less ergonomic API)

#### 4. LiteLLM vs LangChain for AI Provider

- **Choice:** LiteLLM
- **Rationale:**
  - Simple, focused on provider abstraction
  - Lightweight, no unnecessary features
  - Easy to switch providers
  - Good error handling
- **Alternative:** LangChain (more features than needed, heavier)

#### 5. Rich vs Textual for TUI

- **Choice:** Rich
- **Rationale:**
  - Simpler API for our needs
  - Excellent terminal rendering
  - Progress bars, tables, panels
  - Can build lightweight TUI
- **Alternative:** Textual (full TUI framework, more complex than needed)

## Data Flow & State Management

### Configuration Flow

1. **First Run:** Check for `~/.config/iptax/settings.yaml`
1. **If Missing:** Run interactive questionnaire ([`iptax config`](../src/iptax/cli.py))
1. **Validate:** Check did config, AI provider, etc.
1. **Save:** Write validated configuration

### History Tracking

**Location:** `~/.cache/iptax/history.json`

**Purpose:**

- Track cut-off dates for each monthly report
- Prevent duplicate or missing changes
- Enable regeneration of past reports

**Schema:**

```json
{
  "2024-10": {
    "last_cutoff_date": "2024-10-26",
    "generated_at": "2024-10-26T14:30:00"
  }
}
```

### AI Judgment Cache

**Location:** `~/.cache/iptax/ai_cache.json`

**Purpose:**

- Cache AI filtering decisions
- Learn from user overrides
- Reduce API calls

**Schema:**

```json
{
  "cache_version": "1.0",
  "judgments": {
    "owner/repo#123": {
      "decision": "INCLUDE",
      "user_decision": "INCLUDE",
      "reasoning": "Implements serverless feature X",
      "user_reasoning": null,
      "product": "Acme Fungear",
      "timestamp": "2024-11-01T10:30:00Z"
    }
  }
}
```

## Security Considerations

### Credential Management

1. **Never Store Passwords:** Use environment variables or system authentication
1. **API Keys:** Load from environment variables only
1. **Browser Sessions:** Keep in memory, clear after use
1. **File Permissions:** Settings files should be `600` (user-only)

### Data Privacy

1. **Local Only:** All data stored locally on user's machine
1. **No Cloud Storage:** PDFs and reports stay on local filesystem
1. **AI Requests:** Only PR/MR descriptions sent to AI (no personal data)

### Security Tools

The project uses ruff with security checks enabled:

- **S (flake8-bandit):** Security vulnerability scanner
- **TRY:** Exception handling best practices

## Performance Considerations

### Target Metrics

- **Startup time:** \<2 seconds
- **Config load time:** \<100ms
- **did fetch time:** \<30 seconds (network dependent)
- **AI batch filtering:** \<20 seconds for 50 changes
- **PDF generation:** \<10 seconds total
- **Memory usage:** \<500MB peak

### Optimization Strategies

1. **Caching:** AI judgments, did responses
1. **Batch Processing:** AI filtering in single request
1. **Lazy Loading:** Import heavy dependencies only when needed
1. **Streaming:** Process large datasets iteratively

## Error Handling Philosophy

### Principles

1. **Clear Error Messages:** Always explain what went wrong
1. **Suggest Solutions:** Provide actionable recovery steps
1. **Graceful Degradation:** Fall back to manual input when automation fails
1. **Preserve Data:** Never lose user work on errors
1. **Logging:** Detailed logs for debugging

### Error Categories

1. **Configuration Errors:** Missing or invalid settings
1. **Integration Errors:** did, Workday, AI provider failures
1. **File System Errors:** Permission denied, disk full
1. **Network Errors:** Timeouts, connection failures
1. **User Input Errors:** Invalid dates, malformed data

See [Edge Cases](edge-cases.md) for detailed error scenarios and handling.

## Type Safety

The project uses Python type hints extensively:

```python
from typing import Optional, List
from pydantic import BaseModel

class Settings(BaseModel):
    employee_name: str
    supervisor_name: str
    product_name: str
    creative_work_percentage: int
    output_dir: str
```

**Tools:**

- **mypy:** Static type checker
- **pydantic:** Runtime type validation
- **ruff (ANN):** Enforce type annotations

## Testing Architecture

See [Testing](testing.md) for detailed testing strategy.

**Key Points:**

- Unit tests for business logic
- E2E tests for critical paths
- Mocking external dependencies (AI, Workday, did)
- Make-based test orchestration with guard files
