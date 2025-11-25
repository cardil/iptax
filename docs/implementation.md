# Implementation Phases

This document describes the implementation phases, timeline, and development workflow
for the iptax tool.

**See also:**

- [Main Documentation](project.md) - Project overview and onboarding
- [Requirements](requirements.md) - Detailed requirements
- [Architecture](architecture.md) - Technical design
- [Workflows](workflows.md) - Detailed workflow steps
- [Testing](testing.md) - Testing strategy
- [Edge Cases](edge-cases.md) - Error handling scenarios
- [Examples](examples.md) - Configuration and usage examples

______________________________________________________________________

## Phase Overview

The project will be implemented in 4 phases, each delivering incremental value and
building on the previous phase.

______________________________________________________________________

## Phase 1: Foundation & Core Infrastructure (Week 1-2)

**Goal:** Establish project structure, configuration system, and basic CLI

### Deliverables

1. Project structure setup (src/, tests/, docs/)
1. Configuration management (settings.yaml loading, validation)
1. History tracking (history.toml operations)
1. Basic CLI framework (Click commands, help system)
1. Unit tests for config and history

### Success Criteria

- `iptax config` creates and validates settings
- `iptax history` displays (empty) history
- `make unit` passes all config/history tests
- Documentation in place

### Key Files

- [`src/iptax/cli.py`](../src/iptax/cli.py) - CLI entry point
- `src/iptax/config/` - Configuration management package
  - `base.py` - Settings loading and validation
  - `interactive.py` - Interactive configuration wizard
- `src/iptax/history.py` - History operations
- `src/iptax/models.py` - Data models
- [`Makefile`](../Makefile:1) - Build orchestration
- [`pyproject.toml`](../pyproject.toml:1) - Dependencies

______________________________________________________________________

## Phase 2: Data Collection & Integration (Week 3-4)

**Goal:** Integrate with did SDK and implement change fetching

### Deliverables

1. did SDK integration
1. Change extraction and parsing
1. Date range calculation logic
1. Provider selection from ~/.did/config
1. Emoji cleaning from PR titles
1. Unit and integration tests

### Success Criteria

- Can fetch changes from configured did providers
- Date range calculated correctly from history
- Changes properly extracted with metadata
- Multi-month span detection works
- `make unit` passes all did integration tests

### Key Files

- `src/iptax/did_integration.py` - did SDK wrapper
- `tests/unit/test_did_integration.py` - Tests
- `tests/fixtures/sample_did_output.py` - Mock data

______________________________________________________________________

## Phase 3: AI Filtering & Review (Week 5-6)

**Goal:** Implement AI-assisted filtering with TUI review

### Deliverables

1. AI provider integration (LiteLLM)
1. Batch judgment processing
1. Judgment cache system
1. TUI-based review interface (Rich)
1. User override and reasoning
1. Comprehensive tests with mocked AI

### Success Criteria

- AI batch filtering works for multiple providers
- Cache correctly stores and retrieves judgments
- TUI displays compact list and detail views
- User can navigate and override decisions
- UNCERTAIN/ERROR changes force manual review
- `make unit` and `make e2e` pass

### Key Files

- `src/iptax/ai_filter.py` - AI filtering logic
- `src/iptax/tui.py` - TUI components
- `tests/unit/test_ai_filter.py` - Tests
- `tests/fixtures/sample_ai_cache.json` - Mock cache

______________________________________________________________________

## Phase 4: Report Generation & Polish (Week 7-8)

**Goal:** Complete report generation and finalize all features

### Deliverables

1. Workday integration (Playwright) with fallback
1. Report compiler (Markdown formatting)
1. PDF generation (WeasyPrint, bilingual templates)
1. Work hours calculation
1. Complete e2e tests
1. Documentation (installation, usage, troubleshooting)

### Success Criteria

- Can generate all 3 output files (MD + 2 PDFs)
- PDFs are bilingual and properly formatted
- Workday integration works or falls back gracefully
- History updated correctly after generation
- `make verify` passes completely
- User documentation complete

### Key Files

- `src/iptax/workday.py` - Workday client
- `src/iptax/report_compiler.py` - Report compilation
- `src/iptax/pdf_generator.py` - PDF generation
- `src/iptax/templates/` - HTML templates
- `tests/e2e/test_full_workflow.py` - E2E tests
- `docs/` - User documentation

______________________________________________________________________

## Timeline & Milestones

```text
Week 1-2: Phase 1 - Foundation
├── M1.1: Project setup complete
├── M1.2: Config system working
└── M1.3: Basic CLI functional

Week 3-4: Phase 2 - Data Collection
├── M2.1: did integration working
├── M2.2: Change extraction complete
└── M2.3: Date range logic validated

Week 5-6: Phase 3 - AI & Review
├── M3.1: AI filtering operational
├── M3.2: TUI review working
└── M3.3: Cache system functional

Week 7-8: Phase 4 - Reports & Polish
├── M4.1: All reports generating
├── M4.2: Workday integration done
├── M4.3: Documentation complete
└── M4.4: Ready for release
```

______________________________________________________________________

## Development Workflow

### Complete Feature/Bugfix Development Cycle

```bash
# 1. Start with clean state
make clean

# 2. Initialize development environment
make init

# 3. Develop feature/bugfix
# ... make code changes ...

# 4. Format code
make format

# 5. Run relevant tests
make unit  # or make e2e

# 6. Full verification before committing
make verify

# 7. Create feature/bugfix branch
git checkout -b feature/your-feature-name
# or
git checkout -b fix/your-bugfix-name

# 8. Stage and commit changes (only modified files)
git add src/iptax/your_file.py tests/unit/test_your_file.py
git commit -m "feat: add batch AI filtering with YAML responses"

# Commit message format:
# - feat: new feature
# - fix: bug fix
# - docs: documentation changes
# - test: test additions/changes
# - refactor: code refactoring

# 9. Push to remote
git push origin feature/your-feature-name

# 10. Create pull request using GitHub CLI
gh pr create --title "Add batch AI filtering" \
  --body "Implements batch filtering with YAML responses and TUI review"

# Or use interactive mode:
gh pr create

# 11. Monitor CI checks
gh pr checks --watch

# Wait until all checks pass:
# ✓ Linting passed
# ✓ Tests passed
# ✓ Build successful

# 12. Get review comments
gh pr view

# 13. If corrections needed, make changes
# ... edit files ...
make verify
git add .
git commit -m "address review comments: improve error handling"
git push

# Re-check
gh pr checks --watch

# 14. Merge when approved and all checks pass
gh pr merge

# Choose merge strategy:
# - Squash and merge (recommended for features)
# - Create a merge commit
# - Rebase and merge

# 15. Clean up
git checkout main
git pull
git branch -d feature/your-feature-name
```

### Branch Strategy

- `main` - Stable, deployable code
- `develop` - Integration branch
- `feature/*` - Feature branches
- `fix/*` - Bug fix branches

### Pull Request Requirements

- `make verify` must pass before creating PR
- All CI checks must pass
- Code review by at least one person
- All review conversations resolved
- Documentation updated if needed

______________________________________________________________________

## Risk Mitigation

### Technical Risks

#### 1. did SDK API Changes

- **Mitigation:** Pin specific version, monitor upstream
- **Fallback:** Wrapper layer isolates SDK changes

#### 2. AI Provider Rate Limits

- **Mitigation:** Aggressive caching, exponential backoff
- **Fallback:** Manual review mode (`--skip-ai`)

#### 3. Workday UI Changes

- **Mitigation:** Flexible selectors, error handling
- **Fallback:** Manual hours input always available

#### 4. PDF Generation Complexity

- **Mitigation:** Start with simple templates, iterate
- **Fallback:** Focus on Markdown first, PDFs later

### Schedule Risks

#### 1. Feature Creep

- **Mitigation:** Strict phase boundaries, MVP focus
- **Response:** Defer non-critical features to v2

#### 2. Integration Challenges

- **Mitigation:** Early integration tests, mocking
- **Buffer:** Week 8 has built-in buffer time

______________________________________________________________________

## Definition of Done

### For Each Phase

- All planned deliverables completed
- Unit tests written and passing
- Integration/e2e tests passing
- Code reviewed and merged
- Documentation updated
- `make verify` passes
- Demo to stakeholders successful

### For Final Release

- All 4 phases complete
- Full e2e workflow tested manually
- User documentation complete
- Installation tested on fresh system
- README with quick start guide
- GitHub release created with notes

______________________________________________________________________

## Success Metrics

### Development Metrics

- `make verify` pass rate: 100%
- Test coverage: >80% for core logic
- Build time: \<2 minutes
- CI pipeline duration: \<5 minutes

### User Metrics

- Time to first successful report: \<10 minutes
- Report generation time: \<3 minutes
- Configuration completion rate: >90%
- User satisfaction: >4/5

______________________________________________________________________

## Post-Release Plan

### v1.0 Scope

- Core features as defined in phases 1-4
- Support for Gemini and Vertex AI
- GitHub and GitLab via did
- Workday integration with SAML
- Bilingual PDF reports

### Future Enhancements (v2.0+)

- Additional AI providers (OpenAI, Anthropic)
- Additional time tracking integrations
- Report templates customization
- Multi-language support (beyond Polish/English)
- Web UI for report review
- Report submission automation
- Analytics and insights

______________________________________________________________________

## Getting Help

### For Development Issues

1. Check existing issues: `gh issue list`
1. Search documentation: `docs/`
1. Ask in discussions: `gh discussion list`
1. Create new issue: `gh issue create`

### For Testing Issues

1. Run with verbose: `pytest -v`
1. Check logs: `pytest --log-cli-level=DEBUG`
1. Review test fixtures: `tests/fixtures/`
1. Consult [Testing](testing.md) documentation
