# Configuration & Usage Examples

This document provides practical examples of configurations, workflows, and usage
patterns for the iptax tool.

**See also:**

- [Main Documentation](project.md) - Project overview and onboarding
- [Requirements](requirements.md) - Detailed requirements
- [Architecture](architecture.md) - Technical design
- [Workflows](workflows.md) - Detailed workflow steps
- [Testing](testing.md) - Testing strategy
- [Implementation](implementation.md) - Development phases
- [Edge Cases](edge-cases.md) - Error handling scenarios

______________________________________________________________________

## Sample Configuration Files

### Full Configuration Example

**File:** `~/.config/iptax/settings.yaml`

```yaml
# Employee Information
employee:
  name: "Jane Smith"
  supervisor: "John Doe"

# Product Configuration
product:
  name: "Acme Fungear"

# Report Generation Settings
report:
  output_dir: "~/Documents/iptax/{year}/"
  creative_work_percentage: 80

# AI Provider Configuration
ai:
  provider: "gemini"
  model: "gemini-1.5-flash"
  api_key_env: "GEMINI_API_KEY"

# Work Hours Provider
workday:
  enabled: true
  url: "https://workday.company.com"
  auth: "saml"

# psss/did Configuration
did:
  config_path: "~/.did/config"
  providers:
    - "github.com"
    - "gitlab.cee"

# Output directory structure:
# {year} is replaced with report year
# ~/Documents/iptax/2024/
# ~/Documents/iptax/2025/
```

### Minimal Configuration (No AI, No Workday)

**File:** `~/.config/iptax/settings.yaml`

```yaml
employee:
  name: "Jane Developer"
  supervisor: "John Manager"

product:
  name: "Cool Open Source Project"

report:
  output_dir: "~/Documents/iptax/{year}/"
  creative_work_percentage: 75

ai:
  provider: null  # Disabled

workday:
  enabled: false

did:
  config_path: "~/.did/config"
  providers:
    - "github.com"
```

### Vertex AI Configuration

**File:** `~/.config/iptax/settings.yaml`

```yaml
employee:
  name: "Cloud Developer"
  supervisor: "Tech Lead"

product:
  name: "Enterprise Platform"

report:
  output_dir: "~/Documents/iptax/{year}/"
  creative_work_percentage: 80

ai:
  provider: "vertex"
  project_id: "my-gcp-project"
  location: "us-central1"
  model: "gemini-1.5-flash"

workday:
  enabled: false

did:
  config_path: "~/.did/config"
  providers:
    - "github.com"
    - "gitlab.cee"
```

______________________________________________________________________

## Command Examples

### Basic Usage

```bash
# Generate report for current month (most common)
iptax

# Same as above (explicit command)
iptax report

# Generate report for specific month
iptax report --month 2024-10

# Generate report for previous month
iptax report --month 2024-11
```

### Advanced Usage

```bash
# Generate without AI filtering (manual review all)
iptax report --skip-ai

# Generate without Workday (manual hours input)
iptax report --skip-workday

# Preview without creating files
iptax report --dry-run

# Force regenerate existing report
iptax report --month 2024-10 --force

# Custom output directory
iptax report --output-dir ~/my-reports/

# Verbose mode for debugging
iptax report --verbose

# Quiet mode (errors only)
iptax report --quiet

# Combination of options
iptax report --month 2024-10 --skip-ai --skip-workday --force
```

### Configuration Management

```bash
# Initial setup
iptax config

# Validate current configuration
iptax config --validate

# Show current configuration
iptax config --show

# Edit specific field
iptax config --edit employee.name
iptax config --edit ai.provider
iptax config --edit report.output_dir
```

### History Management

```bash
# Show all report history
iptax history

# Show specific month
iptax history --month 2024-10

# Output as JSON
iptax history --format json

# Output as YAML
iptax history --format yaml
```

______________________________________________________________________

## Workflow Examples

### First-Time Setup Workflow

```bash
# 1. Install the tool
pip install iptax

# 2. Configure did (if not already done)
did --config ~/.did/config

# 3. Run interactive configuration
iptax config

# Follow the prompts:
# - Enter employee name
# - Enter supervisor name
# - Enter product name
# - Set creative work percentage
# - Configure AI provider (or skip)
# - Configure Workday (or skip)
# - Select did providers

# 4. Generate your first report
iptax

# You'll be prompted for:
# - Previous month's cutoff date
# - Working hours (if Workday not configured)
# - Review AI decisions (if AI configured)

# 5. Check the generated files
ls ~/Documents/iptax/2024/
```

### Monthly Report Generation Workflow

```bash
# On the 26th of each month, run:
iptax

# The tool will:
# 1. Calculate date range from last report's cutoff
# 2. Fetch changes from did
# 3. Filter changes using AI
# 4. Get working hours from Workday (or prompt)
# 5. Generate 3 files (MD + 2 PDFs)
# 6. Update history

# Review the generated files
ls ~/Documents/iptax/2024/

# Files created:
# - 2024-11 IP TAX Report.md
# - 2024-11 IP TAX Work Card.pdf
# - 2024-11 IP TAX Raport.pdf
```

### Regeneration Workflow

```bash
# If you need to regenerate a report
iptax report --month 2024-10

# Tool will ask:
# Report for October 2024 already exists.
# Regenerate? [y/N]:

# Answer 'y' to proceed

# The tool will:
# - Use same cutoff date as before
# - Fetch latest changes
# - Re-run AI filtering
# - Generate new files (overwriting old ones)
# - Update history with regenerated_at timestamp
```

______________________________________________________________________

## Sample Outputs

### Markdown Report

**File:** `2024-11 IP TAX Report.md`

<!-- editorconfig-checker-disable -->

```markdown
## Changes

* [WASM driver (redhat/serverless#1234)](https://github.com/redhat/serverless/pull/1234)
* [Knative eventing (redhat/serverless#1256)](https://github.com/redhat/serverless/pull/1256)
* [Knative documentation (redhat/docs#9012)](https://github.com/redhat/docs/pull/9012)
* [Fix memory leak (redhat/openshift-serverless#1278)](https://github.com/redhat/openshift-serverless/pull/1278)

## Projects

* [redhat / serverless](https://github.com/redhat/serverless)
* [redhat / docs](https://github.com/redhat/docs)
```

<!-- editorconfig-checker-enable -->

### History File

**File:** `~/.cache/iptax/history.toml`

```toml
["2024-10"]
last_cutoff_date = "2024-10-26"
generated_at = "2024-10-26T14:30:00Z"

["2024-11"]
last_cutoff_date = "2024-11-25"
generated_at = "2024-11-26T09:30:00Z"
regenerated_at = "2024-11-30T11:00:00Z"

["2024-12"]
last_cutoff_date = "2024-12-26"
generated_at = "2024-12-27T10:15:00Z"
```

### AI Judgment Cache

**File:** `~/.cache/iptax/ai_cache.json`

```json
{
  "cache_version": "1.0",
  "judgments": {
    "redhat/serverless#1234": {
      "url": "https://github.com/redhat/serverless/pull/1234",
      "description": "Add serverless function runtime",
      "decision": "INCLUDE",
      "user_decision": "INCLUDE",
      "reasoning": "Directly implements new runtime for OpenShift Serverless",
      "user_reasoning": null,
      "product": "Acme Fungear",
      "timestamp": "2024-11-26T09:30:00Z",
      "ai_provider": "gemini-1.5-pro"
    },
    "cncf/people#1290": {
      "url": "https://github.com/cncf/people/pull/1290",
      "description": "Add user to Ambassadors list",
      "decision": "INCLUDE",
      "user_decision": "EXCLUDE",
      "reasoning": "Infrastructure change, seems related",
      "user_reasoning": "This is community work, not product development",
      "product": "Acme Fungear",
      "timestamp": "2024-11-26T09:32:00Z",
      "ai_provider": "gemini-1.5-pro"
    }
  }
}
```

______________________________________________________________________

## Troubleshooting Examples

### Problem: did Not Configured

**Error:**

```
Error: ~/.did/config not found
```

**Solution:**

```bash
# Configure did first
did --config ~/.did/config

# Then configure iptax
iptax config
```

### Problem: Invalid AI API Key

**Error:**

```
Error: Invalid Gemini API key
```

**Solution:**

```bash
# Get a new API key from:
# https://aistudio.google.com/app/apikey

# Set the environment variable
export GEMINI_API_KEY="your-new-api-key"

# Verify configuration
iptax config --validate
```

### Problem: Workday Authentication Fails

**Error:**

```
Error: Workday authentication failed
```

**Solution:**

```bash
# Renew Kerberos ticket
kinit username@REALM

# Or skip Workday and use manual hours
iptax report --skip-workday
```

### Problem: No Changes Found

**Error:**

```
No changes found for 2024-11-26 to 2024-12-25
```

**Solution:**

```bash
# Check did configuration
cat ~/.did/config

# Test did directly
did --since 2024-11-26 --until 2024-12-25

# Verify providers are correct
iptax config --show
```

______________________________________________________________________

## Development Examples

### Running Tests

```bash
# Initialize development environment
make init

# Run all tests
make test

# Run only unit tests
make unit

# Run only e2e tests
make e2e

# Run specific test file
pytest tests/unit/test_config.py

# Run with coverage
make coverage

# Open coverage report
open htmlcov/index.html
```

### Code Quality Checks

```bash
# Format code
make format

# Run linter
make lint

# Run type checker
make typecheck

# Run all checks
make verify
```

### Creating a Feature

```bash
# 1. Create feature branch
git checkout -b feature/my-feature

# 2. Make changes
# ... edit files ...

# 3. Format and test
make format
make verify

# 4. Commit changes
git add .
git commit -m "feat: add my awesome feature"

# 5. Push and create PR
git push origin feature/my-feature
gh pr create
```

______________________________________________________________________

## Environment Variable Examples

```bash
# AI Provider API Keys
export GEMINI_API_KEY="your-gemini-api-key"
export OPENAI_API_KEY="your-openai-api-key"

# Google Cloud credentials (for Vertex AI)
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/credentials.json"
export GCP_PROJECT_ID="my-gcp-project"

# Custom configuration paths
export IPTAX_CONFIG_DIR="~/.config/iptax"
export IPTAX_CACHE_DIR="~/.cache/iptax"

# Debug mode
export IPTAX_DEBUG="1"
export IPTAX_LOG_LEVEL="DEBUG"
```

______________________________________________________________________

## Directory Structure Examples

### Typical Project Structure

```text
~/.config/iptax/
└── settings.yaml

~/.cache/iptax/
├── history.toml
└── ai_cache.json

~/.did/
└── config

~/Documents/iptax/
├── 2024/
│   ├── 2024-10 IP TAX Report.md
│   ├── 2024-10 IP TAX Work Card.pdf
│   ├── 2024-10 IP TAX Raport.pdf
│   ├── 2024-11 IP TAX Report.md
│   ├── 2024-11 IP TAX Work Card.pdf
│   └── 2024-11 IP TAX Raport.pdf
└── 2025/
    ├── 2025-01 IP TAX Report.md
    ├── 2025-01 IP TAX Work Card.pdf
    └── 2025-01 IP TAX Raport.pdf
```

### Development Project Structure

```text
iptax-reporter/
├── .git/
├── .gitignore
├── .make/                  # Guard files
│   ├── init.done
│   ├── venv.done
│   ├── unit.passed
│   └── e2e.passed
├── src/
│   └── iptax/
│       ├── __init__.py
│       ├── cli.py
│       ├── config/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   └── interactive.py
│       └── ...
├── tests/
│   ├── unit/
│   ├── e2e/
│   └── fixtures/
├── docs/
│   ├── project.md
│   ├── requirements.md
│   ├── architecture.md
│   ├── workflows.md
│   ├── testing.md
│   ├── implementation.md
│   ├── edge-cases.md
│   └── examples.md
├── pyproject.toml
├── Makefile
├── README.md
└── LICENSE
```

______________________________________________________________________

## Integration Examples

### GitHub Actions CI

```yaml
# .github/workflows/test.yml
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

### Pre-commit Hook

```bash
# .git/hooks/pre-commit
#!/bin/bash

echo "Running pre-commit checks..."

# Format code
make format

# Run linter
make lint

# Run unit tests
make unit

if [ $? -ne 0 ]; then
  echo "Pre-commit checks failed. Please fix errors and try again."
  exit 1
fi

echo "Pre-commit checks passed!"
exit 0
```

______________________________________________________________________

## Quick Reference

### Common Commands

| Command                        | Description                        |
| ------------------------------ | ---------------------------------- |
| `iptax`                        | Generate report for current month  |
| `iptax report --month YYYY-MM` | Generate report for specific month |
| `iptax config`                 | Interactive configuration          |
| `iptax config --show`          | Show current configuration         |
| `iptax history`                | Show report history                |
| `make init`                    | Initialize development environment |
| `make verify`                  | Run all checks and tests           |
| `make format`                  | Format code                        |
| `make unit`                    | Run unit tests                     |

### Important Files

| File                            | Purpose            |
| ------------------------------- | ------------------ |
| `~/.config/iptax/settings.yaml` | Main configuration |
| `~/.cache/iptax/history.toml`   | Report history     |
| `~/.cache/iptax/ai_cache.json`  | AI judgment cache  |
| `~/.did/config`                 | did configuration  |
| `~/Documents/iptax/{year}/`     | Generated reports  |

### Common Paths

| Path                 | Description              |
| -------------------- | ------------------------ |
| `~/.config/iptax/`   | Configuration directory  |
| `~/.cache/iptax/`    | Cache directory          |
| `~/Documents/iptax/` | Default output directory |
| `~/.did/config`      | did configuration file   |
