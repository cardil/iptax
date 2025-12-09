# IP Tax Reporter (iptax)

[![CI][ci-badge]][ci-link] [![Python 3.11+][py-badge]][py-link]
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

Automated IP tax report generator for Polish software developers participating in the
50% tax deduction program for creative work.

## Features

- 🔍 **Automatic change collection** - Fetches merged PRs/MRs from GitHub/GitLab via
  [psss/did](https://github.com/psss/did)
- 🤖 **AI-assisted filtering** - Uses Gemini or Vertex AI to identify product-related
  changes
- 📊 **Workday integration** - Retrieves work hours via SSO+Kerberos or manual input
- 📄 **Bilingual PDF reports** - Generates Polish/English tax reports and work cards
- 📚 **History tracking** - Prevents duplicate reporting with automatic date range
  management

## Installation

### Prerequisites

- Python 3.11 or higher
- [did](https://github.com/psss/did) configured with your GitHub/GitLab credentials

### System Dependencies

The tool requires system libraries for PDF generation (WeasyPrint) and browser
automation (Playwright Firefox).

**Fedora/RHEL/CentOS (dnf):**

```bash
sudo dnf install -y pango gdk-pixbuf2 gtk3 dbus-glib libXt alsa-lib
```

**Ubuntu/Debian (apt):**

```bash
sudo apt install -y libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 \
    libgtk-3-0 libdbus-glib-1-2 libxt6 libasound2
```

**macOS (Homebrew):**

```bash
brew install pango gdk-pixbuf gtk+3 dbus
```

### Using pipx (Recommended)

```bash
pipx install iptax
```

### Using uvx (No Install)

Run directly without installation:

```bash
uvx iptax config
uvx iptax
```

### From Source (Development)

```bash
git clone https://github.com/cardil/iptax.git
cd iptax
make init  # Creates venv and installs dependencies
```

## Quick Start

### 1. Configure did

If you haven't already, configure did with your GitHub/GitLab credentials:

```bash
# Create ~/.did/config with your settings
did --config ~/.did/config
```

Example `~/.did/config`:

```ini
[general]
email = your.email@example.com

[github]
type = github
url = https://api.github.com
token = ghp_your_token_here
login = your-github-username
```

### 2. Configure iptax

Run the interactive configuration wizard:

```bash
iptax config
```

This will prompt you for:

- Your full name (for reports)
- Product name (the project you're reporting on)
- AI provider settings (Gemini API key or Vertex AI project)
- Workday URL (optional)
- Creative work percentage (default: 100%)

### 3. Generate Your First Report

```bash
# Generate report for current month
iptax

# Or specify a month
iptax --month 2024-11
```

## Usage

### Main Commands

```bash
# Full report flow (collect → AI filter → review → generate)
iptax [--month YYYY-MM]

# Collect data only (PRs and work hours)
iptax collect [--month YYYY-MM]

# Review AI judgments interactively
iptax review [--month YYYY-MM]

# Generate output files from collected data
iptax dist [--month YYYY-MM]
```

### Configuration Commands

```bash
# Interactive configuration
iptax config

# Show current configuration
iptax config --show

# Validate configuration
iptax config --validate

# Show config file path
iptax config --path
```

### Cache Management

```bash
# List in-flight reports
iptax cache list

# Show cache statistics
iptax cache stats

# Clear caches
iptax cache clear [--ai] [--inflight] [--month YYYY-MM]

# Show cache paths
iptax cache path
```

### History

```bash
# Show report history
iptax history

# Show specific month
iptax history --month 2024-11

# Output as JSON/YAML
iptax history --format json
```

### Options

| Option           | Description                                               |
| ---------------- | --------------------------------------------------------- |
| `--month`        | Target month (auto-detect, 'current', 'last', or YYYY-MM) |
| `--skip-ai`      | Skip AI filtering                                         |
| `--skip-review`  | Skip interactive review                                   |
| `--skip-workday` | Skip Workday integration                                  |
| `--force`        | Discard existing in-flight data                           |
| `--output-dir`   | Override output directory                                 |
| `--format`       | Output format (all, md, pdf)                              |

## Output Files

The tool generates three files in `~/Documents/iptax/YYYY/`:

1. **Markdown Report** (`YYYY-MM IP TAX Report.md`)

   - List of all included changes with links
   - Grouped by repository

1. **Work Card PDF** (`YYYY-MM IP TAX Work Card.pdf`)

   - Bilingual (Polish/English) document
   - Lists product changes for tax authorities

1. **Tax Report PDF** (`YYYY-MM IP TAX Raport.pdf`)

   - Official monthly report
   - Work hours calculation
   - Copyright transfer declaration

## Configuration

Configuration is stored in `~/.config/iptax/settings.yaml`:

```yaml
# User information
author:
  full_name: "Jan Kowalski"

# Product being reported
product:
  name: "OpenShift Serverless"

# AI provider (gemini or vertex_ai)
ai:
  provider: gemini
  model: gemini-2.0-flash
  api_key: "your-api-key"

# Workday integration (optional)
workday:
  enabled: true
  url: "https://wd3.myworkday.com/yourcompany"
  auth: sso+kerberos
  trusted_uris:
    - "https://sso.yourcompany.com"

# Output settings
output:
  directory: "~/Documents/iptax"
  creative_work_percentage: 100
```

## How It Works

1. **Date Range Calculation** - Determines the reporting period based on history and
   Polish tax law timing (26th-25th cycles)

1. **Change Collection** - Uses `did` to fetch merged PRs/MRs from configured
   GitHub/GitLab sources

1. **AI Filtering** - Sends changes to AI for relevance judgment, with caching to reduce
   API calls

1. **Interactive Review** - TUI interface for reviewing and overriding AI decisions

1. **Work Hours** - Retrieves hours from Workday or accepts manual input

1. **Report Generation** - Compiles data into markdown and bilingual PDF reports

1. **History Update** - Records the report to prevent duplicate changes in future
   reports

## Development

### Setup

```bash
# Clone repository
git clone https://github.com/cardil/iptax.git
cd iptax

# Initialize development environment
make init

# Run tests
make verify
```

### Make Targets

| Target        | Description                        |
| ------------- | ---------------------------------- |
| `make init`   | Initialize development environment |
| `make verify` | Run all checks and tests           |
| `make test`   | Run unit and e2e tests             |
| `make unit`   | Run unit tests only                |
| `make e2e`    | Run e2e tests only                 |
| `make check`  | Run lints and type checks          |
| `make format` | Format code                        |
| `make clean`  | Clean build artifacts              |

### Project Structure

```
iptax/
├── src/iptax/           # Source code
│   ├── ai/              # AI filtering and cache
│   ├── cache/           # History and in-flight caches
│   ├── cli/             # Command-line interface
│   ├── config/          # Configuration management
│   ├── report/          # PDF/Markdown generation
│   ├── utils/           # Utilities
│   └── workday/         # Workday integration
├── tests/               # Test suite
│   ├── unit/            # Unit tests
│   └── e2e/             # End-to-end tests
├── docs/                # Documentation
└── Makefile             # Build automation
```

## Troubleshooting

### Configuration Issues

```bash
# Validate configuration
iptax config --validate

# Check config file location
iptax config --path
```

### AI Cache Issues

```bash
# Clear AI cache if judgments seem wrong
iptax cache clear --ai
```

### Workday Authentication

For SSO+Kerberos issues:

1. Ensure you have a valid Kerberos ticket: `klist`
1. Try with visible browser: `iptax workday --foreground`
1. Use password fallback: `iptax workday --no-kerberos`

### did Integration

```bash
# Test did configuration
did --since 2024-11-01 --until 2024-11-30

# Check did config location
cat ~/.did/config
```

## Contributing

1. Fork the repository
1. Create a feature branch: `git checkout -b feature/my-feature`
1. Make changes and test: `make verify`
1. Commit with conventional commits: `git commit -m "feat: add feature"`
1. Push and create PR: `gh pr create`

## License

Apache 2.0 License - See [LICENSE](LICENSE) for details.

## Acknowledgments

- [psss/did](https://github.com/psss/did) - Change tracking tool
- [WeasyPrint](https://weasyprint.org/) - PDF generation
- [Playwright](https://playwright.dev/) - Browser automation
- [LiteLLM](https://github.com/BerriAI/litellm) - AI provider abstraction
- [Rich](https://rich.readthedocs.io/) - Terminal UI
- [Textual](https://textual.textualize.io/) - TUI framework

<!-- Badge links -->

[ci-badge]: https://github.com/cardil/iptax/actions/workflows/ci.yml/badge.svg
[ci-link]: https://github.com/cardil/iptax/actions/workflows/ci.yml
[py-badge]: https://img.shields.io/badge/python-3.11+-blue.svg
[py-link]: https://www.python.org/downloads/
