# Edge Cases & Error Handling

This document describes edge cases and error handling strategies for the iptax tool.

**See also:**
- [Main Documentation](project.md) - Project overview and onboarding
- [Requirements](requirements.md) - Detailed requirements
- [Architecture](architecture.md) - Technical design
- [Workflows](workflows.md) - Detailed workflow steps
- [Testing](testing.md) - Testing strategy
- [Implementation](implementation.md) - Development phases
- [Examples](examples.md) - Configuration and usage examples

---

## Error Handling Philosophy

### Principles

1. **Clear Error Messages:** Always explain what went wrong
2. **Suggest Solutions:** Provide actionable recovery steps
3. **Graceful Degradation:** Fall back to manual input when automation fails
4. **Preserve Data:** Never lose user work on errors
5. **Logging:** Detailed logs for debugging

---

## Configuration Edge Cases

### Missing or Invalid ~/.did/config

**Scenario:** User runs `iptax` without configuring did first

**Behavior:**
```bash
Error: ~/.did/config not found

Please configure 'did' first by running:
  did --config ~/.did/config

Then run 'iptax config' to configure iptax.
```

**Test Case:**
```python
def test_missing_did_config(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    result = runner.invoke(cli, ['config'])
    assert result.exit_code == 1
    assert "~/.did/config not found" in result.output
```

### Empty Providers in ~/.did/config

**Scenario:** did config exists but has no providers configured

**Behavior:**
```bash
Error: No providers configured in ~/.did/config

Please enable at least one provider in your did config:
  [github]
  type = github
  url = https://github.com
  ...

Then run 'iptax config' again.
```

### Invalid AI Credentials

**Scenario:** User provides AI credentials that fail validation

**Behavior:**
```bash
Error: Invalid Gemini API key

The API key you provided failed authentication.

Please verify your API key at:
  https://aistudio.google.com/app/apikey

Enter Gemini API key (or 'skip' to configure later):
```

**Test Case:**
```python
def test_invalid_ai_credentials(monkeypatch):
    monkeypatch.setattr('litellm.completion', 
                       Mock(side_effect=AuthenticationError()))
    
    result = runner.invoke(cli, ['config'], 
                          input='gemini\nINVALID_KEY\nskip\n')
    assert "Invalid Gemini API key" in result.output
    assert result.exit_code == 0
```

---

## History Tracking Edge Cases

### First Report Ever (No History)

**Scenario:** User runs `iptax report` for the first time

**Behavior:**
```bash
This is your first report. To calculate the date range,
I need to know when your previous report ended.

Enter the last cutoff date (YYYY-MM-DD) [2024-11-25]:
```

### Multi-Month Gap in History

**Scenario:** User skipped November, now generating December report

**Behavior:**
```bash
Warning: Date range spans 61 days (2024-10-26 to 2024-12-25)

This likely means you skipped generating reports for:
  - November 2024

Options:
  [C]ontinue with this range (may include too many changes)
  [A]djust start date manually
  [G]enerate missing month reports first
  [Q]uit

Choice:
```

### Regenerating Existing Month

**Scenario:** User wants to regenerate October report

**Behavior:**
```bash
Report for October 2024 already exists.

Generated on: 2024-10-26 10:00:00
Cutoff date: 2024-10-25

[R]egenerate (overwrites existing files)
[C]ancel

Choice:
```

### Corrupted History File

**Scenario:** history.toml has invalid TOML syntax

**Behavior:**
```bash
Error: Cannot parse ~/.cache/iptax/history.toml

TOML syntax error on line 5: Expected '='

Options:
  [B]ackup and create new history (safe)
  [F]ix manually (advanced)
  [Q]uit

Choice:
```

---

## did Integration Edge Cases

### No Changes in Period

**Scenario:** did returns empty results for the date range

**Behavior:**
```bash
No changes found for 2024-11-26 to 2024-12-25

This could mean:
  - No PRs/MRs were merged in this period
  - Your did providers are not configured correctly
  - The date range is incorrect

Do you want to:
  [C]ontinue anyway (generate report with no changes)
  [A]djust date range
  [V]erify did configuration
  [Q]uit

Choice:
```

### did Provider Failure

**Scenario:** GitHub provider returns 401 Unauthorized

**Behavior:**
```bash
Error: GitHub authentication failed

Provider: github.com
Error: 401 Unauthorized

Possible causes:
  - GitHub token expired or invalid
  - Token lacks required scopes (repo, read:org)
  - Token was revoked

Please update your token in ~/.did/config:
  [github]
  token = YOUR_NEW_TOKEN

Generate a new token at:
  https://github.com/settings/tokens

Required scopes: repo, read:org
```

### Malformed PR Title with Emoji

**Scenario:** PR title is "🎉 feat: Add new feature 🚀"

**Behavior:**
- Extract PR title from did response
- Clean emoji using regex or emoji library
- Store cleaned title: "feat: Add new feature"
- Preserve URL and metadata

**Test Case:**
```python
def test_emoji_cleaning():
    title = "🎉 feat: Add feature 🚀"
    cleaned = clean_title(title)
    assert cleaned == "feat: Add feature"
    assert not any(c in cleaned for c in '🎉🚀')
```

---

## AI Filtering Edge Cases

### All Changes Uncertain

**Scenario:** AI returns UNCERTAIN for every change

**Behavior:**
```bash
AI Review Results: 0 included, 0 excluded, 25 uncertain

All changes require manual review. For each change:
  - Read the AI rationale
  - Decide: [I]nclude or [E]xclude
  - Optionally add your reasoning

Press any key to start review...
```

### AI Provider Timeout

**Scenario:** AI request takes >60 seconds and times out

**Behavior:**
```bash
Error: AI request timed out

The AI provider took too long to respond.

Options:
  [R]etry with longer timeout (120s)
  [S]kip AI filtering (manual review all)
  [Q]uit and try later

Choice:
```

### Invalid YAML Response from AI

**Scenario:** AI returns malformed YAML that can't be parsed

**Behavior:**
```bash
Error: AI returned invalid response

The AI provider's response could not be parsed.
This is likely a temporary issue.

Options:
  [R]etry (ask AI again)
  [S]kip AI (manual review all)
  [D]ebug (show raw response)
  [Q]uit

Choice:
```

### AI Cache Corruption

**Scenario:** ai_cache.json has invalid JSON syntax

**Behavior:**
```bash
Warning: AI cache is corrupted

File: ~/.cache/iptax/ai_cache.json
Error: JSON decode error on line 42

[B]ackup and create new cache (lose AI judgments)
[F]ix manually (advanced)
[I]gnore and continue without cache

Choice:
```

---

## Workday Integration Edge Cases

### SAML Authentication Failure

**Scenario:** Kerberos ticket expired, can't authenticate

**Behavior:**
```bash
Error: Workday authentication failed

Could not complete SAML login automatically.

This usually means:
  - Your Kerberos ticket expired
  - You need to login manually
  - MFA is required

Please renew your Kerberos ticket:
  kinit username@REALM

Or, enter working hours manually:
  Enter total working hours for period [168]:
```

### Workday UI Changed

**Scenario:** Workday updated UI, selectors no longer work

**Behavior:**
```bash
Error: Cannot extract hours from Workday

Workday's UI may have changed. The tool could not
locate the working hours element.

Please file an issue at:
  https://github.com/user/iptax/issues

Include the URL you were redirected to.

For now, enter hours manually:
  Enter total working hours [168]:
```

### Headless Browser Not Available

**Scenario:** Playwright not installed or browser missing

**Behavior:**
```bash
Error: Playwright browser not installed

To use Workday integration, install Playwright:
  pip install playwright
  playwright install chromium

Or, skip Workday and enter hours manually:
  Enter total working hours [168]:
```

---

## Report Generation Edge Cases

### Output Directory Not Writable

**Scenario:** User's output directory has no write permissions

**Behavior:**
```bash
Error: Cannot write to ~/Documents/iptax/2024/

Permission denied. Please check:
  - Directory exists and is writable
  - No other process has files locked
  - Disk space is available

Options:
  [C]hange output directory
  [F]ix permissions (need sudo)
  [Q]uit

Choice:
```

### Disk Space Full

**Scenario:** No space left on device when writing PDFs

**Behavior:**
```bash
Error: Not enough disk space

Successfully created:
  ✓ Markdown report

Failed to create:
  ✗ Work Card PDF
  ✗ Tax Report PDF

Please free up disk space and re-run:
  iptax report --month 2024-11

The markdown file is already saved, so PDFs will
generate quickly on next run.
```

### PDF Generation Failure (WeasyPrint Error)

**Scenario:** WeasyPrint fails to render template

**Behavior:**
```bash
Error: PDF generation failed

WeasyPrint encountered an error:
  Missing font: 'Arial'
  Line 42 in work_card.html

Please install required fonts or use fallback:
  [R]etry with fallback fonts
  [S]kip PDF generation (markdown only)
  [D]ebug (show full error)
  [Q]uit

Choice:
```

---

## Date & Time Edge Cases

### Month Boundary Precision

**Scenario:** Report generated on last day vs first day of next month

**Example:**
- Previous: 2024-10-25
- Current: Generate on 2024-11-01
- Date range: 2024-10-26 to 2024-11-01 (7 days)
- This is correct and expected

### Timezone Handling

**Behavior:**
- Always use local timezone for date calculations
- Store dates in history as YYYY-MM-DD (no timezone)
- Store timestamps in history as UTC ISO 8601
- Display dates to user in local timezone

### Leap Year Handling

**Behavior:**
- Use standard library datetime for all date math
- Python automatically handles leap years
- No special code needed

---

## Command Line Edge Cases

### Invalid Month Format

**Scenario:** User types `iptax report --month November`

**Behavior:**
```bash
Error: Invalid month format 'November'

Please use YYYY-MM format, for example:
  iptax report --month 2024-11
  iptax report --month 2024-12

Or omit --month to generate for current month.
```

### Future Month Request

**Scenario:** User asks for report for next month

**Behavior:**
```bash
Error: Cannot generate future report

Requested: 2024-12
Current: 2024-11

You can only generate reports for:
  - Current month (2024-11)
  - Past months (2024-10, 2024-09, ...)
```

---

## Internationalization Edge Cases

### Non-ASCII Characters in Names

**Scenario:** Employee name is "Krzysztof Suszyński" (Polish chars)

**Behavior:**
- Store name as UTF-8 in settings.yaml
- Render correctly in PDFs using Unicode fonts
- Ensure WeasyPrint uses UTF-8 encoding

### Month Names in Both Languages

**Scenario:** Generate report for October (Październik in Polish)

**Behavior:**
- Maintain month name mapping in code
- Render both in PDF: "October / Październik 2024"
- Ensure correct declension for Polish

---

## Performance Edge Cases

### Large Number of Changes (>200)

**Scenario:** User has 250 merged PRs in the period

**Behavior:**
- Fetch all changes from did (may take 30-60s)
- Display progress indicator
- AI batch filtering (single request, <30s)
- TUI paginated view (show 20 at a time)
- Generate report with all changes
- Monitor memory usage (<500MB)

### Slow Network Connection

**Scenario:** did fetch takes 2+ minutes due to slow network

**Behavior:**
- Show progress spinner during fetch
- Allow user to cancel (Ctrl+C)
- Handle KeyboardInterrupt gracefully
- Clean up partial data
- Exit with code 130

---

## Security Edge Cases

### API Keys in Error Messages

**Scenario:** Error occurs while using AI, traceback might expose key

**Behavior:**
- Catch all exceptions globally
- Sanitize error messages before display
- Never log full API keys
- Use key prefix for identification (e.g., "sk-***")

**Implementation:**
```python
def sanitize_error(msg: str) -> str:
    """Remove potential API keys from error messages"""
    return re.sub(r'[A-Za-z0-9]{32,}', '***REDACTED***', msg)
```

### File Permission Issues

**Scenario:** Settings file created with wrong permissions (777)

**Behavior:**
- Create config directory with 700 permissions
- Create settings.yaml with 600 permissions
- Verify permissions on load
- Warn if insecure permissions detected

---

## Recovery Strategies

### General Recovery Steps

1. **Check Logs:** Review error messages and logs
2. **Verify Config:** Run `iptax config --validate`
3. **Check Dependencies:** Ensure did, AI provider configured
4. **Clean Cache:** Remove `~/.cache/iptax/` and retry
5. **Fresh Install:** `make clean install`

### When All Else Fails

1. Create issue with:
   - Full error message
   - Steps to reproduce
   - Configuration (sanitized)
   - Environment details
2. Use verbose mode: `iptax report --verbose`
3. Check existing issues: `gh issue list`
4. Ask in discussions: `gh discussion list`

---

## Error Code Reference

| Exit Code | Meaning |
|-----------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Invalid usage (wrong arguments) |
| 130 | User cancelled (Ctrl+C) |