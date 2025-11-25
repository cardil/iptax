# Workflows & CLI Design

This document describes the detailed workflows and CLI design for the iptax tool.

**See also:**
- [Main Documentation](project.md) - Project overview and onboarding
- [Requirements](requirements.md) - Detailed requirements  
- [Architecture](architecture.md) - Technical design
- [Testing](testing.md) - Testing strategy
- [Implementation](implementation.md) - Development phases
- [Edge Cases](edge-cases.md) - Error handling scenarios
- [Examples](examples.md) - Configuration and usage examples

---

## Main Report Generation Workflow

The main `iptax report` command follows this workflow:

### Step 1: Initialize & Validate

```text
1.1 Load configuration from ~/.config/iptax/settings.yaml
    - If config doesn't exist → run interactive setup (iptax config)
    - Validate all required fields

1.2 Check if ~/.did/config exists
    - If missing → guide user to configure did first
    - Verify providers are configured

1.3 Load history from ~/.cache/iptax/history.toml
    - If file doesn't exist → this is the first report

1.4 Determine reporting month:
    - If --month specified → use that month (format: YYYY-MM)
    - Else → use current month (from current date)

1.5 Check if report for this month already exists in history:
    - If exists → warn user and ask to regenerate
    - If user declines → exit
    - If user accepts → proceed with regeneration
```

### Step 2: Calculate Date Range

```text
2.1 Determine START date:
    - If history has previous month's report:
      start_date = previous_report.last_cutoff_date + 1 day
      
    - If NO previous report (first run):
      Prompt user: "Enter cutoff date for previous month (YYYY-MM-DD):"
      start_date = user_input + 1 day

2.2 Determine END date:
    - end_date = current date (when tool is executed)

2.3 Validate date range:
    - If range > 31 days → warn about multi-month span
    - Ensure start_date <= end_date

2.4 Display date range to user:
    "Generating report for: [start_date] to [end_date] ([X] days)"
```

### Step 3: Fetch Changes from did SDK

```text
3.1 Initialize did SDK
3.2 Fetch changes using SDK (not shell-out)
3.3 Handle errors (missing config, auth failures, etc.)
3.4 Process changes:
    - Extract all changes with metadata
    - Extract all unique repositories
    - Clean PR/MR titles: remove GitHub emoji codes
3.5 Display summary: "✓ Found [N] changes across [M] repositories"
```

### Step 4: Get Work Hours

```text
4.1 Check if Workday is enabled in config
4.2 If enabled: Try automated retrieval
    - Launch headless browser
    - Authenticate via SAML
    - Extract hours
    - On failure: fall back to manual input
4.3 If disabled or failed: Manual hours input
4.4 Calculate creative work hours:
    creative_hours = total_hours × (creative_work_percentage / 100)
4.5 Display summary
```

### Step 5: AI-Assisted Filtering (TUI Review)

```text
5.1 Check if --skip-ai flag is set
5.2 Initialize AI provider
5.3 Load judgment cache
5.4 Build batch prompt with history and current changes
5.5 Send batch request to AI
5.6 Parse AI response
5.7 Handle errors (mark as ERROR if AI fails)
5.8 Display compact list with decisions
5.9 Check if auto-accept possible (no UNCERTAIN/ERROR)
5.10 If needed: Launch detailed TUI review
5.11 Save updated cache
5.12 Display filtering summary
```

### Step 6: Generate Reports

```text
6.1 Prepare output directory
6.2 Generate Markdown Report
6.3 Generate Work Card PDF
6.4 Generate Tax Report PDF
6.5 Display success message with file paths
```

### Step 7: Update History

```text
7.1 Create history entry for this month
7.2 Write to ~/.cache/iptax/history.toml
7.3 Display completion message
7.4 Final summary with next steps
```

---

## CLI Design

### Command Structure

```bash
iptax [COMMAND] [OPTIONS]
```

**Available Commands:**
- `(no command)` - Default, equivalent to `iptax report` for current month
- `report` - Generate IP tax report
- `config` - Configure settings interactively
- `history` - Show report history
- `--help` - Show help message
- `--version` - Show version and exit

### Report Command

**Usage:**
```bash
iptax report [OPTIONS]
iptax [OPTIONS]  # same as above
```

**Options:**
```text
--month YYYY-MM          Generate report for specific month (default: current)
--skip-ai                Skip AI filtering, manually review all changes
--skip-workday           Skip Workday integration, use manual hours input
--dry-run                Show what would be generated without creating files
--force                  Overwrite existing report without confirmation
--output-dir PATH        Custom output directory (overrides config)
--verbose, -v            Verbose output (show API calls, debug info)
--quiet, -q              Minimal output (errors only)
```

**Examples:**

```bash
# Generate report for current month (most common use case)
iptax

# Generate report for specific month
iptax report --month 2024-10

# Generate without AI filtering
iptax report --skip-ai

# Generate with manual hours input
iptax report --skip-workday

# Preview without creating files
iptax report --dry-run

# Force regenerate existing report
iptax report --month 2024-10 --force

# Custom output directory
iptax report --output-dir ~/my-reports/

# Verbose mode for debugging
iptax report --verbose

# Combination of options
iptax report --month 2024-10 --skip-ai --skip-workday --force
```

### Config Command

**Usage:**
```bash
iptax config [OPTIONS]
```

**Options:**
```text
--validate               Validate current configuration
--show                   Display current configuration
--edit FIELD             Edit specific field interactively
```

**Examples:**

```bash
# Interactive setup (first time or full reconfiguration)
iptax config

# Validate current settings
iptax config --validate

# Show current configuration
iptax config --show

# Edit specific field
iptax config --edit employee.name
iptax config --edit ai.provider
```

**Interactive Questionnaire Flow:**
```text
Welcome to iptax configuration!

Employee Information:
  Employee name: [current or empty]
  > Krzysztof Suszyński

  Supervisor name: [current or empty]
  > Vaclav Tunka

Product Configuration:
  Product name: [current or empty]
  > Red Hat OpenShift Serverless

Report Settings:
  Creative work percentage (0-100) [80]:
  > 80

  Output directory [~/Documents/iptax/{year}/]:
  > (press Enter for default)

AI Provider:
  Provider (gemini/vertex) [gemini]:
  > gemini

  Model [gemini-1.5-pro]:
  > (press Enter for default)

  API key environment variable [GEMINI_API_KEY]:
  > (press Enter for default)

Workday Integration:
  Enable Workday integration? [y/N]:
  > n

psss/did Configuration:
  did config path [~/.did/config]:
  > (press Enter for default)

  Reading ~/.did/config...
  Found providers:
    [1] github.com (enabled)
    [2] gitlab.cee (enabled)
    [3] gitlab (enabled)

  Select providers to use (comma-separated numbers or 'all') [all]:
  > 1,2,3

Testing configuration...
  ✓ did config found with 3 selected providers
  ✓ AI provider connection successful

Configuration saved to ~/.config/iptax/settings.yaml
```

### History Command

**Usage:**
```bash
iptax history [OPTIONS]
```

**Options:**
```text
--month YYYY-MM          Show specific month only
--format FORMAT          Output format: table, json, yaml (default: table)
```

**Examples:**

```bash
# Show all report history
iptax history

# Show specific month
iptax history --month 2024-10

# Output as JSON
iptax history --format json
```

**Example Output (Table Format):**
```text
Report History
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Month      Cutoff Date  Generated At         Regenerated
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
2024-09    2024-09-25   2024-09-26 10:30:00  -
2024-10    2024-10-26   2024-10-26 14:15:00  -
2024-11    2024-11-15   2024-11-15 09:00:00  2024-11-25
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Next report will start from: 2024-11-16
```

---

## TUI Review Interface

### Compact List View

```text
Changes Review (navigate: ↑↓, select: Enter, done: d)
────────────────────────────────────────────────────
> ✓ Fix memory leak (knative/hack#436)
  ✓ Add Go 1.22 support (knative/toolbox#040)
  ✗ Add user to Ambassadors (cncf/people#1290)
  ✓ Implement feature X (knative/serving#1234)
  ? Cannot determine (internal/tool#567)        ← needs review
  ! API timeout (gitlab/project#890)            ← needs review
  ✓ Bug fix in operator (knative/operator#234)
────────────────────────────────────────────────────
[6/15] INCLUDE: 6, EXCLUDE: 2, UNCERTAIN: 1, ERROR: 1
[↑↓] navigate [Enter] details [f] flip [d] done

Legend: ✓=INCLUDE ✗=EXCLUDE ?=UNCERTAIN !=ERROR
```

### Detail View

```text
════════════════════════════════════════════════════
Change Details [5/15]
════════════════════════════════════════════════════

Title: Cannot determine relevance
Repo: internal/tool#567
URL: https://internal-gitlab.com/internal/tool/-/merge_requests/567

Description:
[Full PR/MR description here, may be multiple lines]

────────────────────────────────────────────────────
AI Decision: UNCERTAIN
AI Reasoning: Cannot access internal GitLab to determine
             if this relates to the product

Current Decision: UNCERTAIN ← needs your input
────────────────────────────────────────────────────

[i]nclude [e]xclude [r]easoning [b]ack [n]ext [p]rev

Command: _
```

### Navigation Commands

**List View:**
- `↑↓` - Navigate up/down
- `Enter` - View details for selected change
- `f` - Flip decision (INCLUDE ↔ EXCLUDE)
- `d` - Mark as done (only if no UNCERTAIN/ERROR remain)
- `q` - Quit (ask to save if changes made)

**Detail View:**
- `i` - Set decision to INCLUDE
- `e` - Set decision to EXCLUDE
- `r` - Add/edit reasoning for your decision
- `b` - Back to list view
- `n` - Next change details
- `p` - Previous change details
- `q` - Quit to list view

---

## Error Handling Throughout Workflow

**General Principles:**
- Always validate user input
- Provide clear error messages with suggested solutions
- Allow graceful fallbacks (e.g., Workday → manual input)
- Never lose user data (cache decisions immediately)
- Log errors for debugging

See [Edge Cases](edge-cases.md) for detailed error scenarios.