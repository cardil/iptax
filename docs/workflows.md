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

______________________________________________________________________

## Date Range Timing Logic

### Automatic Date Range Calculation

The tool automatically determines which month to report based on **Polish legal
requirements**: employee payments must be made before the 10th of the following month.

**Default behavior (no `--month` specified):**

1. **If run on days 1-10 of any month:**

   - Reports for **PREVIOUS month**
   - Both Workday and Did use the same date range (previous month)
   - Example: Run on Dec 5 → Reports November (Nov 1-30 for both WD and Did)

1. **If run on days 11-31 of any month:**

   - Reports for **CURRENT month**
   - Workday: Full current calendar month
   - Did: From last recorded cutoff (or 25th of previous month) to today
   - Example: Run on Nov 25 → Reports November
     - Workday: Nov 1-30
     - Did: Last cutoff from history, or Oct 25 fallback → Nov 25

**Why this logic?**

Polish law requires employee payments before the 10th of the next month. This creates a
natural reporting window:

- Early in the month (1-10): Finalize the previous month's report
- Rest of the month (11-31): Work on the current month's report

The Did range captures work from the last ~30 days to avoid missing any changes, while
Workday reports the full calendar month (users must fill hours ahead of time, which is
unavoidable).

### Manual Month Selection

**Using `--month` parameter:**

```bash
--month YYYY-MM          # Specific month (e.g., 2024-11)
--month current          # Force current month regardless of date
--month last            # Force previous month regardless of date
```

When `--month` is specified, it overrides the automatic detection but still applies the
appropriate date range logic for that month.

### Fine-Tuning Date Ranges

For companies with different policies, you can override the automatic calculations:

```bash
--workday-start YYYY-MM-DD    # Override Workday start date
--workday-end YYYY-MM-DD      # Override Workday end date
--did-start YYYY-MM-DD        # Override Did start date
--did-end YYYY-MM-DD          # Override Did end date
```

**Examples:**

```bash
# Use automatic detection (most common)
iptax report

# Force report for November regardless of today's date
iptax report --month 2024-11

# Report for current month even if it's Dec 5
iptax report --month current

# Custom date ranges for special cases
iptax report --month 2024-11 --did-start 2024-10-20 --did-end 2024-11-25

# Override only Workday dates
iptax report --workday-start 2024-11-01 --workday-end 2024-11-28
```

______________________________________________________________________

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

1.3 Load history from ~/.cache/iptax/history.json
    - If file doesn't exist → this is the first report

1.4 Determine reporting month:
    - If --month specified → use that month (format: YYYY-MM)
    - Else → use current month (from current date)

1.5 Check if report for this month already exists in history:
    - If exists → warn user and ask to regenerate
    - If user declines → exit
    - If user accepts → proceed with regeneration
```

### Step 2: Calculate Date Ranges

```text
2.1 Calculate Workday date range:
    - start_date = first day of specified month
    - end_date = last day of specified month

2.2 Calculate Did date range (from history or fallback):
    - If history has a previous report:
      start_date = cutoff_date from the last report in history
    - If NO previous report (first run):
      start_date = 25th of month before specified month (fallback)
    - end_date:
      * Days 1-10 (finalization): last day of specified month
      * Days 11-31 (active work): today (when tool is executed)

2.3 Validate date ranges:
    - Ensure start_date <= end_date for both ranges
    - If Did range > 60 days → warn about multi-month span

2.4 Display date ranges to user:
    "Workday: [start] to [end] (full month)"
    "Changes: [start] to [end] ([X] days since last report)"
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

### Step 4: Get Work Hours and Validate

**⚠️ CRITICAL: Workday data MUST be validated before use. Failing to report correct work
hours is a misdemeanor under Polish law.**

```text
4.1 Check if Workday is enabled in config
4.2 If enabled: Try automated retrieval
    - Launch headless browser
    - Authenticate via SAML
    - Extract calendar entries for date range
    - On failure: fall back to manual input

4.3 VALIDATE Workday data (MANDATORY):
    - Check ALL workdays in month have entries (work hours OR PTO)
    - List any missing days explicitly
    - If gaps found:
      * Display missing days to user
      * Prompt: "Continue with incomplete data?" or "Enter hours manually?"
      * User MUST explicitly acknowledge gaps or provide manual entry
    - If validation fails and user declines to continue:
      * Abort and instruct user to fill Workday first

4.4 If disabled or validation failed: Manual hours input
    - Prompt for total hours
    - Prompt for absence/PTO days

4.5 Calculate creative work hours:
    creative_hours = total_hours × (creative_work_percentage / 100)

4.6 Display summary with validation status:
    "✓ Workday data validated: complete coverage for [month]"
    or
    "⚠ Manual hours used (Workday incomplete or disabled)"
```

**Why validation is critical:**

Polish law requires accurate reporting of work hours for tax purposes. Submitting
incorrect hours is a legal violation (misdemeanor). The validation step ensures:

1. All workdays in the reporting period are accounted for
1. User explicitly confirms any gaps or provides correct data
1. Compliance with legal requirements for accurate reporting

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
7.2 Write to ~/.cache/iptax/history.json
7.3 Display completion message
7.4 Final summary with next steps
```

______________________________________________________________________

## CLI Design

### Command Structure

```bash
iptax [COMMAND] [OPTIONS]
```

**Available Commands:**

- `(no command)` - Default, equivalent to `iptax report` for current month
- `collect` - Collect data (Did PRs and Workday) without AI/review
- `review` - Review in-flight data interactively
- `report` - Complete flow: collect → AI filter → review → display
- `cache` - Manage in-flight cache (show status, clear, etc.)
- `config` - Configure settings interactively
- `history` - Show report history
- `--help` - Show help message
- `--version` - Show version and exit

### Collect Command

**Usage:**

```bash
iptax collect [OPTIONS]
```

**Options:**

```text
--month YYYY-MM|current|last    Month to collect data for (default: auto-detect)
--workday-start YYYY-MM-DD      Override Workday start date
--workday-end YYYY-MM-DD        Override Workday end date
--did-start YYYY-MM-DD          Override Did start date
--did-end YYYY-MM-DD            Override Did end date
--skip-workday                  Skip Workday integration
--skip-did                      Skip Did integration (PRs/MRs)
--force                         Force re-collection even if data exists
```

**Examples:**

```bash
# Collect data for auto-detected month
iptax collect

# Collect for specific month
iptax collect --month 2024-11

# Collect for last month (override auto-detection)
iptax collect --month last

# Collect only Did data (skip Workday)
iptax collect --skip-workday

# Collect only Workday data (skip Did)
iptax collect --skip-did

# Custom Did date range
iptax collect --did-start 2024-10-20 --did-end 2024-11-25

# Force re-collection
iptax collect --force
```

**What it does:**

1. Auto-detects which month to report (or uses --month)
1. Calculates date ranges (with Polish legal logic or custom overrides)
1. Checks for existing in-flight data
1. Fetches Did PRs/MRs (unless --skip-did)
1. Fetches Workday hours (unless --skip-workday)
1. Saves to in-flight cache
1. Displays summary and next steps

### Review Command

**Usage:**

```bash
iptax review
```

**What it does:**

1. Loads in-flight data
1. Runs AI filtering if not already done
1. Launches interactive TUI for review
1. Saves results back to cache

### Report Command

**Usage:**

```bash
iptax report [OPTIONS]
iptax [OPTIONS]  # same as above (default command)
```

**Options:**

```text
--month YYYY-MM|current|last    Generate report for specific month
                                (default: auto-detect)
--workday-start YYYY-MM-DD      Override Workday start date
--workday-end YYYY-MM-DD        Override Workday end date
--did-start YYYY-MM-DD          Override Did start date
--did-end YYYY-MM-DD            Override Did end date
--skip-ai                       Skip AI filtering, manually review all changes
--skip-workday                  Skip Workday integration
--skip-review                   Skip interactive review (auto-accept AI decisions)
--force-new                     Force new collection, discard in-flight data
```

**Examples:**

```bash
# Complete flow for auto-detected month (most common use case)
iptax
iptax report

# Report for specific month
iptax report --month 2024-10

# Force report for last month
iptax report --month last

# Skip AI filtering (manual review only)
iptax report --skip-ai

# Skip Workday integration
iptax report --skip-workday

# Skip interactive review (auto-accept)
iptax report --skip-review

# Force new collection
iptax report --force-new

# Custom date ranges
iptax report --month 2024-11 --did-start 2024-10-20 --did-end 2024-11-25

# Combination of options
iptax report --month 2024-10 --skip-ai --skip-workday
```

**Workflow:**

1. Collect data (or load from in-flight cache)
1. Run AI filtering (unless --skip-ai)
1. Interactive review (unless --skip-review)
1. Display final results

### Cache Command

**Usage:**

```bash
iptax cache [SUBCOMMAND]
```

**Subcommands:**

```text
list                     List all in-flight cache entries
clear [--month YYYY-MM]  Clear in-flight cache (all or specific month)
--path                   Show path to cache directory
```

**Examples:**

```bash
# List all cache entries
iptax cache list

# Clear all in-flight cache
iptax cache clear

# Clear cache for specific month only
iptax cache clear --month 2024-11

# Show cache directory path
iptax cache --path
```

**What it does:**

- `list`: Displays information about all cached in-flight data (month, date ranges, data
  collected, etc.)
- `clear`: Removes in-flight cached data (prompts for confirmation)
- `clear --month YYYY-MM`: Removes only the cache for the specified month
- `--path`: Displays the path to the cache directory

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
  > Jane Smith

  Supervisor name: [current or empty]
  > John Doe

Product Configuration:
  Product name: [current or empty]
  > Acme Fungear

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

______________________________________________________________________

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

______________________________________________________________________

## Error Handling Throughout Workflow

**General Principles:**

- Always validate user input
- Provide clear error messages with suggested solutions
- Allow graceful fallbacks (e.g., Workday → manual input)
- Never lose user data (cache decisions immediately)
- Log errors for debugging

See [Edge Cases](edge-cases.md) for detailed error scenarios.
