# Requirements & Core Features

This document contains the detailed requirements and core features of the iptax tool.

**See also:**

- [Main Documentation](project.md) - Project overview and onboarding
- [Architecture](architecture.md) - Technical design and structure
- [Workflows](workflows.md) - Detailed workflow steps
- [Testing](testing.md) - Testing strategy
- [Implementation](implementation.md) - Development phases
- [Edge Cases](edge-cases.md) - Error handling scenarios
- [Examples](examples.md) - Configuration and usage examples

______________________________________________________________________

## Executive Summary

**Tool Name:** `iptax`\
**Purpose:** Automate monthly IP tax report generation for Polish software developers
participating in the IP tax deduction program (50% tax deduction for copyright income).

**Key Features:**

- Integrates with psss/did to automatically fetch merged PRs/MRs
- AI-assisted filtering of changes to match configured product
- Optional Workday integration for work hours retrieval
- Generates bilingual (Polish/English) PDF reports
- Maintains history to prevent duplicate reporting
- Interactive configuration and review workflow

**Primary Users:** Polish software developers working on open-source/FOSS projects who
need to file monthly IP tax reports.

______________________________________________________________________

## Project Overview

### Background

Polish tax law provides a 50% tax deduction for copyright income. Software developers
contributing to FOSS projects can claim this deduction by submitting monthly reports
documenting their creative work. This tool automates the tedious process of:

1. Collecting all merged code contributions from multiple repositories
1. Filtering contributions relevant to a specific product
1. Calculating creative work hours
1. Generating legally compliant bilingual reports

### Problem Statement

Manual report generation involves:

- Running multiple CLI commands to extract PR/MR data
- Manually filtering changes to match product scope
- Calculating work hours from Workday or timesheets
- Creating formatted PDFs with bilingual text
- Tracking which changes were already reported to avoid duplicates

This process takes 2-4 hours monthly and is error-prone.

### Solution Scope

The `iptax` tool will:

- ✅ Automate data collection from GitHub/GitLab via psss/did
- ✅ Use AI to filter changes matching the configured product
- ✅ Integrate with Workday to retrieve work hours (or accept manual input)
- ✅ Generate three output files: markdown report, work card PDF, tax report PDF
- ✅ Track history to prevent duplicate/missing changes between reports
- ✅ Provide interactive configuration and review workflows

The tool will NOT:

- ❌ Submit reports to tax authorities (manual submission required)
- ❌ Perform tax calculations beyond creative work hours
- ❌ Validate legal compliance (assumes user understands requirements)
- ❌ Modify or commit code changes on behalf of the user

______________________________________________________________________

## Core Requirements

### Tool Name & Purpose

**CLI Command:** `iptax`

**Purpose:**\
Generate monthly IP tax reports for the Polish IP tax deduction program by:

1. Fetching merged code contributions from configured repositories
1. Filtering changes to match a specific product using AI assistance
1. Calculating creative work hours
1. Generating bilingual PDF reports with all required legal elements

### Data Sources Integration

#### psss/did Integration

**Repository:** [psss/did](https://github.com/psss/did) **Version Required:** PR #311
(until merged into main)

**Purpose:** Fetch merged PRs/MRs from GitHub/GitLab instances.

**Integration Approach:**

- **Use did as a project dependency** (add to [`pyproject.toml`](../pyproject.toml:1))
- **Call did SDK directly** instead of shell-outs
- Avoid markdown parsing by using did's Python API directly

**Configuration Requirements:**

- User must have `~/.did/config` configured with GitHub/GitLab credentials
- Tool reads this config to determine which providers are enabled
- If no providers configured, guide user to configure did first

**Date Range Calculation:**

- **Start Date:** Last report's `last_cutoff_date` + 1 day (from history file)
- **End Date:** Current date when tool is executed
- For first report: prompt user for previous month cut-off date (default: 25th)

**Important Behavioral Rules:**

1. **Detect Existing Report:** Before generating, check if report for current month
   already exists
1. **User Confirmation:** If exists, ask user if they want to regenerate/continue
1. **No Config Cut-off:** Do NOT store cut-off day in config (removed based on feedback)

**Output Format:** The did SDK will return structured data (not markdown), containing:

- List of changes (PRs/MRs) with descriptions, URLs, and metadata
- List of unique repositories

**Error Handling:**

- did SDK not installed → should not happen (project dependency)
- `~/.did/config` missing → guide user to configure did
- No providers configured → guide user to add providers
- Authentication failures → show did error and suggest re-authentication

#### Workday Integration

**Purpose:** Automatically retrieve working days and hours for the reporting period.

**Approach:** Headless browser automation (Playwright recommended)

**Authentication:**

```yaml
workday:
  enabled: true
  url: "https://workday.company.com"
  auth: "saml"  # Only SAML supported for now
```

**Authentication Flow:**

1. Navigate to Workday URL (from config)
1. Handle SAML authentication via company Keycloak
1. Navigate to timesheet/absence calendar
1. Extract working hours for date range
1. Calculate total working hours
1. Close browser

**Data Needed:**

- Working days in the reporting period
- Absence days (vacation, sick leave)
- Total working hours (typically `working_days × 8`)

**Fallback Mode:** If Workday integration is not configured or fails:

1. Prompt user: "Enter number of working days in \[reporting period\]:"
1. Prompt user: "Enter total working hours (or press Enter for [calculated default]):"
1. Calculate creative work hours based on configured percentage

**Security Considerations:**

- Never store passwords in config files
- Use system authentication (Kerberos/SAML)
- Browser session data stored only in memory, not persisted
- Clear session data after retrieval

**Error Handling:**

- Navigation timeout → fall back to manual input
- Authentication failure → fall back to manual input
- Element not found → fall back to manual input
- Network errors → fall back to manual input

#### AI Provider Integration

**Purpose:** Automatically filter changes to match the configured product using AI
judgment.

**Supported Providers:**

1. **GCP Vertex AI**
1. **Google Gemini API**

**Provider-Agnostic Wrapper:** Use LiteLLM or LangChain to support multiple providers
with a unified interface.

**Batch Filtering Workflow:**

```
1. Load judgment history/cache
2. Collect all changes from did
3. Build batch prompt with:
  - Product name
  - Judgment history (past AI decisions AND human overrides with reasoning)
  - All current changes with full details
4. Send single batch request to AI
5. AI judges all changes at once (not in a loop)
6. Parse AI response for all decisions
7. Display all changes with AI decisions in TUI
8. Quick review: "Accept all AI decisions? [y/n]"
9. If no → navigate through changes, override specific decisions
10. Save updated judgment cache
```

**AI Batch Prompt Template:**

```
Product: {product_name}

Previous Judgment History (for context and learning):
AI decisions and human overrides (with reasoning) are crucial for
performance improvement.

Past Decisions:
- [description] (owner/repo#123)
  AI Decision: INCLUDE
  Human Decision: INCLUDE
  AI Reasoning: implements feature X

- [description] (owner/repo#456)
  AI Decision: INCLUDE
  Human Decision: EXCLUDE
  AI Reasoning: infrastructure change
  Human Reasoning: This is internal tooling, not product work
  (human override)

Current Changes to Judge:
1. owner/repo#789
  URL: https://github.com/owner/repo/pull/789
  Description: [full PR/MR description]

2. owner/repo#790
  URL: https://github.com/owner/repo/pull/790
  Description: [full PR/MR description]

Question: For each change above, determine if it's related to
"{product_name}".

Respond in YAML format (token-efficient):
---
judgments:
  - change_id: owner/repo#789
    decision: INCLUDE  # or EXCLUDE or UNCERTAIN
    reasoning: brief explanation

  - change_id: owner/repo#790
    decision: EXCLUDE
    reasoning: brief explanation

Decision Rules:
- INCLUDE: change directly contributes to this product
- EXCLUDE: change is unrelated to this product
- UNCERTAIN: cannot determine with confidence
```

**Judgment Cache:** Location: `~/.cache/iptax/ai_cache.json` (or `.toml` or `.yaml`)

**Configuration:**

```yaml
ai:
  provider: "gemini"  # or "vertex"
  model: "gemini-1.5-pro"  # or "gemini-1.5-flash"
  api_key_env: "GEMINI_API_KEY"  # environment variable name

  # For Vertex AI:
  # project_id: "my-gcp-project"
  # location: "us-central1"
```

**Interactive Review Process:**

- **IMPORTANT:** This is the ONLY interactive review step
- User reviews AI decisions about which changes to INCLUDE/EXCLUDE
- User does NOT add or remove changes beyond what `did` provided
- User ONLY confirms or overrides AI's filtering decision for each change
- Changes list comes exclusively from the `did` SDK output

**Error Handling (System-Level):**

- API rate limits → mark affected changes with ERROR status, let user decide via TUI
- API errors → mark affected changes with ERROR status, let user decide via TUI
- Invalid API key → prompt user to configure provider before TUI
- Network errors → mark affected changes with ERROR status, let user decide via TUI
- AI unable to judge → AI returns UNCERTAIN, user decides via TUI
- **Note:** ERROR status is set by the system, not by AI

### Configuration Management

#### Settings File

**Location:** `~/.config/iptax/settings.yaml`

**Purpose:** Store user preferences and integration settings (excluding cut-off dates,
which are tracked in history).

**Full Schema:**

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
  output_dir: "~/Documents/iptax/{year}/"  # {year} will be replaced with YYYY
  creative_work_percentage: 80  # Percentage of work considered creative (0-100)

# AI Provider Configuration
ai:
  provider: "gemini"  # Options: "gemini", "vertex"
  model: "gemini-1.5-pro"
  api_key_env: "GEMINI_API_KEY"

  # Vertex AI specific (uncomment if using Vertex AI)
  # project_id: "my-gcp-project"
  # location: "us-central1"

# Work Hours Provider
workday:
  enabled: false  # Set to true to enable Workday integration
  url: ""  # Company Workday URL
  auth: "saml"  # Only SAML supported for now

# psss/did Configuration
did:
  config_path: "~/.did/config"  # Path to did config file
  providers:
    - "github.com"
    - "gitlab.cee"
    - "gitlab"
```

**Validation Rules:**

- [`employee.name`](../pyproject.toml:13) and `employee.supervisor` must be non-empty
  strings
- `product.name` must be non-empty string
- `report.creative_work_percentage` must be between 0-100
- `report.output_dir` must be valid path with optional `{year}` placeholder
- `ai.provider` must be one of: "gemini", "vertex"
- If `workday.enabled = true`, `workday.url` must be valid URL
- `workday.auth` must be "saml" (only supported option)
- `did.config_path` must exist and be readable
- `did.providers` must be non-empty list of provider names from ~/.did/config

#### History File

**Location:** `~/.cache/iptax/history.toml`

**Purpose:** Track cut-off dates for each monthly report to prevent duplicate or missing
changes.

**Critical Concept - Cut-off Date Tracking:**

The history file is the **single source of truth** for determining date ranges for each
report.

**Simplified History Schema:**

```toml
["2024-10"]
last_cutoff_date = "2024-10-26"
generated_at = "2024-10-26T14:30:00Z"

["2024-11"]
last_cutoff_date = "2024-11-25"
generated_at = "2024-11-26T09:30:00Z"
regenerated_at = "2024-11-30T11:00:00Z"  # Optional: if regenerated
```

### Report Output

The tool generates three output files from a single source of truth (the filtered
changes from did):

#### Output Location

**Configurable Directory:**

```yaml
# In settings.yaml
report:
  output_dir: "~/Documents/iptax/{year}/"  # {year} will be replaced with YYYY
  creative_work_percentage: 80
```

**Default:** `~/Documents/iptax/YYYY/`

#### Text Processing Rules

**GitHub Emoji/Icon Removal:** Remove all GitHub emoji codes (pattern: `:[a-z_]+:`) from
PR/MR titles.

#### Markdown Report

**Filename:** `YYYY-MM IP TAX Report.md`\
**Location:** `{output_dir}/YYYY-MM IP TAX Report.md`

**Format:**

```markdown
## Changes

* [Description (owner/repo#number)](https://url)
* ...

## Projects

* [owner / repo](https://url)
* ...
```

#### Work Card PDF

**Filename:** `YYYY-MM IP TAX Work Card.pdf`\
**Location:** `{output_dir}/YYYY-MM IP TAX Work Card.pdf`

**Purpose:** Document the creative work product (changes made during the period).

**Required Sections (Bilingual):**

- Header with work card number and preparation date
- Author Information
- Project List
- Work Description with changes list
- Signatures section

#### Tax Report PDF

**Filename:** `YYYY-MM IP TAX Raport.pdf`\
**Location:** `{output_dir}/YYYY-MM IP TAX Raport.pdf`

**Purpose:** Official monthly report for tax authorities documenting creative work hours
and copyright transfer.

**Required Sections (Bilingual):**

- Header with period
- Employee Information
- Work Hours Calculation
- Co-authors Section
- Product Context
- Copyright Transfer Declaration
- Acceptance Section
