# AI Job Application Agent

Fully autonomous AI agent that discovers, scores, and auto-submits job applications across multiple platforms including LinkedIn, Naukri, Instahyre, Indeed, Greenhouse, Lever, Workday, Ashby, and generic ATS forms.

**Built with reference to:** AIHawk (feder-cr), AutoApply (AbhishekMandapmalvi), job_agentic (algsoch), ApplyPilot (Pickle-Pixel), JobSailor (GoliathReaper), neonwatty/job-apply-plugin, and others.

## Architecture

```
                    ┌──────────┐
                    │  Profile │ (YAML)
                    │ Settings │ (YAML)
                    └────┬─────┘
                         │
┌──────────┐     ┌──────▼──────┐     ┌───────────┐     ┌───────────┐
│ Scrapers │────▶│   Core     │────▶│  Appliers │────▶│  SQLite   │
│ LinkedIn │     │ AnswerEngine│     │ Greenhouse│     │   State   │
│ Naukri   │     │ Scorer     │     │ Lever     │     │           │
│ Instahyre│     │ Deduper    │     │ Workday   │     │           │
│ Indeed   │     │ Profile    │     │ Ashby     │     │           │
│ ATS Det. │     └───────────┘     │ LinkedIn  │     │           │
└──────────┘                       │ Generic   │     └───────────┘
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
cp .env.example .env
# Edit .env with your API keys

# 4. Run
python main.py --discover           # Scrape + score only
python main.py --apply              # Full pipeline
python main.py --apply --dry-run    # Preview without submitting
python main.py --status             # Show stats
python main.py --resume             # Continue from where you left off
```

## Supported Platforms

| Platform | Scraper | Applier | Type |
|----------|---------|---------|------|
| LinkedIn | ✅ | ✅ (Easy Apply) | Job board |
| Naukri | ✅ | ✅ | Job board |
| Instahyre | ✅ | ✅ | Job board |
| Indeed | ✅ | ❌ | Job board |
| Greenhouse | ATS Detect | ✅ | ATS |
| Lever | ATS Detect | ✅ | ATS |
| Workday | ATS Detect | ✅ | ATS |
| Ashby | ATS Detect | ✅ | ATS |
| Generic | ATS Detect | ✅ | Unknown ATS |

## Configuration

**config/profile.yaml** - Your personal information, education, experience, skills, target roles/locations, and resume path.

**config/settings.yaml** - LLM provider settings, scoring thresholds, rate limits per platform, and global options.

**Supported LLM providers:** OpenAI, Anthropic, Google Gemini, local Ollama.

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
- **CAPTCHAs:** Some platforms present CAPTCHAs that will block automated submissions.
- **Form Changes:** ATS platforms frequently update their HTML/CSS. Selectors may break.
- **AI Costs:** Using OpenAI/Anthropic APIs will incur costs for cover letters and screening answers.
- **Data Privacy:** All data stays local on your machine in SQLite. No telemetry.
- **Not Financial Advice:** This tool is for educational and personal use. Verify all applications manually.
