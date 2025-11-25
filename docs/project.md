# IP Tax Reporter - Project Documentation

**Status:** Approved

Welcome to the iptax project documentation! This tool automates monthly IP tax report generation for Polish software developers participating in the IP tax deduction program.

---

## Quick Navigation

### 📚 Core Documentation

- **[Requirements & Core Features](requirements.md)** - Detailed requirements, data sources, and core features
- **[Architecture & Design](architecture.md)** - Technical architecture, design decisions, and technology stack
- **[Workflows](workflows.md)** - CLI interface design and detailed workflow steps
- **[Testing Strategy](testing.md)** - Testing approach, tools, and make-based orchestration
- **[Implementation Phases](implementation.md)** - Development phases, timeline, and workflow
- **[Edge Cases & Error Handling](edge-cases.md)** - Comprehensive error scenarios and recovery strategies
- **[Configuration & Examples](examples.md)** - Sample configurations, commands, and usage patterns

### 🔗 Quick Links

- **[README](../README.md)** - Project README with quick start
- **[Project Specification](requirements.md)** - Start here for detailed requirements
- **[Development Workflow](implementation.md#development-workflow)** - How to contribute
- **[Testing Guide](testing.md)** - How to run tests

---

## Executive Summary

**Tool Name:** `iptax`

**Purpose:** Automate monthly IP tax report generation for Polish software developers by:
- Fetching merged code contributions from GitHub/GitLab via psss/did
- AI-assisted filtering of changes to match configured product
- Optional Workday integration for work hours retrieval  
- Generating bilingual (Polish/English) PDF reports
- Maintaining history to prevent duplicate reporting

**Primary Users:** Polish software developers working on FOSS projects who need to file monthly IP tax reports for the 50% tax deduction program.

---

## Quick Start

### Installation

```bash
# Install from PyPI (when published)
pip install iptax

# Or install from source
git clone https://github.com/cardil/iptax.git
cd iptax
make install

# For development (with test dependencies and editable install)
make init
```

### First-Time Setup

```bash
# 1. Configure did (if not already done)
did --config ~/.did/config

# 2. Run interactive configuration
iptax config

# 3. Generate your first report
iptax
```

### Monthly Usage

```bash
# Generate report for current month (run on the 26th)
iptax

# Review generated files
ls ~/Documents/iptax/2024/
```

See [Examples](examples.md#workflow-examples) for detailed usage examples.

---

## What You Get

The tool generates three output files:

1. **Markdown Report** (`YYYY-MM IP TAX Report.md`)
   - List of all included changes with links
   - List of repositories worked on

2. **Work Card PDF** (`YYYY-MM IP TAX Work Card.pdf`)
   - Bilingual document describing the creative work
   - Required for tax authorities

3. **Tax Report PDF** (`YYYY-MM IP TAX Raport.pdf`)
   - Official monthly report with work hours calculation
   - Copyright transfer declaration
   - Bilingual (Polish/English)

---

## Key Features

### 🤖 AI-Assisted Filtering

- Automatically judges which changes relate to your product
- Learns from your overrides
- Supports Gemini and Vertex AI
- Caches decisions to reduce API calls

### 📊 Workday Integration

- Automatically retrieves work hours via SAML
- Falls back to manual input if needed
- Calculates creative work hours based on percentage

### 📝 Bilingual Reports

- Polish and English text in all PDFs
- Legally compliant format
- Professional PDF generation using WeasyPrint

### 🔄 History Tracking

- Prevents duplicate or missing changes
- Tracks cut-off dates automatically
- Enables report regeneration

---

## Project Structure

```
iptax-reporter/
├── src/iptax/           # Source code
├── tests/               # Test suite
├── docs/                # Documentation (you are here)
│   ├── project.md       # This file - main entry point
│   ├── requirements.md  # Detailed requirements
│   ├── architecture.md  # Technical design
│   ├── workflows.md     # CLI and workflows
│   ├── testing.md       # Testing strategy
│   ├── implementation.md # Development phases
│   ├── edge-cases.md    # Error handling
│   └── examples.md      # Usage examples
├── pyproject.toml       # Project configuration
├── Makefile             # Build orchestration
└── README.md            # Project README
```

---

## Technology Stack

**Language:** Python 3.11+

**Key Dependencies:**
- **CLI:** `click` - Command-line interface framework
- **Terminal UI:** `rich` - Beautiful terminal output and TUI
- **AI:** `litellm` - Multi-provider AI abstraction
- **Browser:** `playwright` - Workday automation
- **PDF:** `weasyprint` - PDF generation from HTML
- **Config:** `pyyaml`, `pydantic` - Configuration management

See [`pyproject.toml`](../pyproject.toml:1) for complete dependency list.

---

## Development Workflow

### Running Tests

```bash
# Initialize development environment
make init

# Run all checks and tests
make verify

# Run only unit tests
make unit

# Run only e2e tests
make e2e

# Run with coverage
make coverage
```

### Code Quality

```bash
# Format code
make format

# Run linter
make lint

# Run type checker
make typecheck
```

### Creating Features

```bash
# 1. Create feature branch
git checkout -b feature/my-feature

# 2. Make changes and test
make verify

# 3. Create pull request
gh pr create

# 4. Monitor CI
gh pr checks --watch
```

See [Implementation](implementation.md#development-workflow) for detailed workflow.

---

## Documentation Guide

### For Users

1. **Getting Started:** Read [Requirements](requirements.md#executive-summary)
2. **Installation:** See [Quick Start](#quick-start) above
3. **Usage Examples:** Check [Examples](examples.md#workflow-examples)
4. **Troubleshooting:** Review [Edge Cases](edge-cases.md)

### For Developers

1. **Architecture:** Read [Architecture](architecture.md)
2. **Workflows:** Understand [Workflows](workflows.md)
3. **Testing:** Follow [Testing Guide](testing.md)
4. **Implementation:** Check [Development Phases](implementation.md)
5. **Contributing:** See [Development Workflow](implementation.md#development-workflow)

### For Reviewers

1. **Requirements:** Verify against [Requirements](requirements.md)
2. **Test Coverage:** Check [Testing Strategy](testing.md)
3. **Error Handling:** Review [Edge Cases](edge-cases.md)
4. **Examples:** Validate [Configuration Examples](examples.md)

---

---

## Getting Help

### Documentation

- **Installation Issues:** See [Examples - Troubleshooting](examples.md#troubleshooting-examples)
- **Configuration Help:** Check [Examples - Configuration](examples.md#sample-configuration-files)
- **Error Messages:** Review [Edge Cases](edge-cases.md)
- **Testing Problems:** Consult [Testing Guide](testing.md)

### Community

- **Issues:** Create an issue on GitHub
- **Discussions:** Use GitHub Discussions
- **Pull Requests:** See [Contributing Guide](implementation.md#development-workflow)

### Useful Commands

```bash
# Get help
iptax --help
iptax report --help
iptax config --help

# Validate configuration
iptax config --validate

# Show current settings
iptax config --show

# View report history
iptax history
```

---

## Success Criteria

### For Users
- Time to first successful report: <10 minutes
- Monthly report generation time: <3 minutes
- Configuration completion rate: >90%

### For Developers
- `make verify` pass rate: 100%
- Test coverage: >80% for core logic
- Build time: <2 minutes

See [Requirements - Success Criteria](requirements.md) for complete metrics.

---

## License

Apache 2.0 License - See [LICENSE](../LICENSE) for details.

---

## References

- **psss/did:** https://github.com/psss/did
- **WeasyPrint:** https://weasyprint.org/
- **Playwright:** https://playwright.dev/
- **LiteLLM:** https://github.com/BerriAI/litellm
- **Rich:** https://rich.readthedocs.io/
