# AI Job Application Agent

Fully autonomous AI agent that discovers, scores, and auto-submits job applications across multiple platforms including LinkedIn, Naukri, Instahyre, Indeed, Greenhouse, Lever, Workday, Ashby, and generic ATS forms.

**Built with reference to:** AIHawk (feder-cr), AutoApply (AbhishekMandapmalvi), job_agentic (algsoch), ApplyPilot (Pickle-Pixel), JobSailor (GoliathReaper), neonwatty/job-apply-plugin, and others.

## Architecture

```
                    ┌──────────┐
                    │  Profile │ (YAML, Pydantic-validated)
                    │ Settings │ (YAML, Pydantic-validated)
                    └────┬─────┘
                         │
┌──────────┐     ┌──────▼──────┐     ┌───────────┐     ┌───────────┐
│ Scrapers │────▶│   Core     │────▶│  Appliers │────▶│  SQLite   │
│ LinkedIn │     │ AnswerEngine│     │ Greenhouse│     │   State   │
│ Naukri   │     │ Scorer     │     │ Lever     │     │           │
│ Instahyre│     │ Deduper    │     │ Workday   │     │           │
│ Indeed   │     │ Profile    │     │ Ashby     │     │           │
│ ATS Det. │     │ Config     │     │ LinkedIn  │     │           │
└──────────┘     └───────────┘     │ Indeed    │     └───────────┘
                                    │ Generic   │
                                    └───────────┘
```

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Install Playwright browser
playwright install chromium

# 3. Configure your profile
cp config/profile.yaml config/profile.yaml
# Edit config/profile.yaml with your details
# (Pydantic validation catches missing fields at startup)
cp .env.example .env
# Edit .env with your API keys

# 4. Run
python main.py --discover           # Scrape + score only
python main.py --apply              # Full pipeline
python main.py --apply --dry-run    # Preview without submitting
python main.py --status             # Show stats (includes auth_required flags)
python main.py --resume             # Continue from where you left off
python main.py --force --apply      # Override lock file if previous run crashed
```

## Supported Platforms

| Platform | Scraper | Applier | Type |
|----------|---------|---------|------|
| LinkedIn | ✅ | ✅ (Easy Apply) | Job board |
| Naukri | ✅ | ✅ | Job board |
| Instahyre | ✅ | ✅ | Job board |
| Indeed | ✅ | ✅ (Quick Apply) | Job board |
| Greenhouse | ATS Detect | ✅ | ATS |
| Lever | ATS Detect | ✅ | ATS |
| Workday | ATS Detect | ✅ | ATS |
| Ashby | ATS Detect | ✅ | ATS |
| Generic | ATS Detect | ✅ | Unknown ATS |

## Configuration

**config/profile.yaml** - Your personal information, education, experience, skills, target roles/locations, and resume path.
- Validated at startup by Pydantic — missing fields fail fast with a clear error.

**config/settings.yaml** - LLM provider settings, scoring thresholds, rate limits, global options, and optional email notification config.

**Supported LLM providers:** OpenAI, Anthropic, Google Gemini, local Ollama.

## New Features

### Selector Resilience (P0.1)
Every scraper and applier now uses 3-5 fallback CSS/XPath selectors per element. When a critical selector (apply button, submit button) fails all fallbacks, a `SelectorNotFoundError` is raised — logged and surfaced in the run summary as a distinct failure reason, clearly distinguishable from "scored below threshold" or "rate limited."

### Login Detection & Per-Platform Skip (P0.2)
If a scraper detects a login/auth wall (URL check + DOM indicators), it:
1. Sets `auth_required = True` for that platform in the DB
2. Skips scraping AND applying on that platform for the rest of the run
3. Reports it prominently in `--status` output and end-of-run summary
4. Does NOT crash the full run — other platforms proceed normally

### CAPTCHA Handling (P0.3)
- CAPTCHA detection in every applier (iframe, recaptcha, data-sitekey checks)
- Per-platform CAPTCHA counter tracked in SQLite + in-memory
- If CAPTCHA count for a platform exceeds `max_captcha_per_run` (default: 3, configurable in settings.yaml), further attempts on that platform stop for the run
- No CAPTCHA-solving integration — flag-and-stop only, as designed

### LLM-Powered Answers (P0.4)
LinkedIn's cover letter, phone, and free-text fields now route through `AnswerEngine` (same as Greenhouse/Lever/Workday/Ashby), so answers are profile-grounded, LLM-generated, and cached in the `llm_cache` table.

### Retry/Backoff (P0.5)
A shared `with_retry()` wrapper in `utils/retry.py` handles transient network/timeout errors with exponential backoff (2 retries, base delay 2s). Used for page navigation — NOT for CAPTCHA or `SelectorNotFoundError` (those fail fast).

### Indeed Applier (P1.6)
Indeed now has a full applier at `appliers/indeed.py` that handles Quick Apply multi-step forms, resume uploads, and external ATS redirect detection. `_get_applier()` registers it explicitly — no silent fall-through to GenericApplier.

### Scheduling (P1.7)
Lock-file protected unattended scheduling:
- **Linux:** `scheduling/cron.sh` — 4-hourly cron job with PID lock
- **Windows:** `scheduling/windows_task.ps1` — PowerShell script to register a Task Scheduler task (every 4 hours, 8 AM start)
- Both exit cleanly if a previous run is still in progress

### Run Summary & Email Notification (P1.8)
Each run generates a JSON summary (`data/run_summaries/run_{id}.json`) with counts by platform:
- Discovered, scored above/below threshold, applied, skipped, failed, captcha_blocked, auth_required
- Optionally emailed via SMTP if configured in `settings.yaml.notify` (opt-in, default off)

### Config Validation (P1.9)
`core/config_models.py` defines Pydantic models for both `profile.yaml` and `settings.yaml`. Validated at startup in `main.py` — a malformed config fails immediately with a clear error listing exactly what's missing or wrong, rather than deep inside an applier at runtime.

### Rotating File Logging (P1.10)
`utils/logger.py` now configures the root logger with a `RotatingFileHandler` (5MB × 5 backups) to `data/logs/agent.log`, plus stdout. All loggers inherit from the root, so there's one consistent log destination.

## Rate Limits

Safety limits per platform per day to avoid account bans:
- LinkedIn: 50 applications/day
- Naukri: 50 applications/day
- Instahyre: 100 applications/day
- Indeed: 50 applications/day
- Company ATS: 100 applications/day

## Limitations & Warnings

- **Terms of Service:** Automated job applications may violate ToS of LinkedIn, Naukri, Indeed, and other platforms. Use at your own risk.
- **Account Suspension:** Aggressive automation can lead to permanent account bans. Respect rate limits.
- **CAPTCHAs:** Some platforms present CAPTCHAs that will block automated submissions. The agent detects these and stops after N attempts per run.
- **Form Changes:** ATS platforms frequently update their HTML/CSS. The multi-fallback selector system is designed to degrade gracefully, but periodic maintenance may be needed.
- **AI Costs:** Using OpenAI/Anthropic APIs will incur costs for cover letters and screening answers.
- **Data Privacy:** All data stays local on your machine in SQLite. No telemetry. Email notification is opt-in only.
- **Not Financial Advice:** This tool is for educational and personal use. Verify all applications manually.
