# appTutorial

An AI-powered, on-screen software tutor for **Windows**. Press a hotkey on a confusing app
(Excel, an IDE, a web app) and appTutorial captures the active window, uses Claude to
identify the app and your intent, and walks you through tasks step by step — verifying each
step against your live screen.

> Status: early development. v1 is being built milestone by milestone (see **SPEC.md**).

## Quick start

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env          # then add your Anthropic Console API key
python -m apptutorial.app       # launches the tray app
```

Verify the scaffold without starting the UI loop:

```powershell
python -m apptutorial.app --check
```

## Anthropic API key

The app calls the Claude API, which needs an **Anthropic Console** key with billing — a
Claude Pro/Max subscription does **not** grant API access. See **CLAUDE.md** for setup.

## Docs

- **SPEC.md** — full product specification and architecture.
- **CLAUDE.md** — working guide, stack, conventions, invariants.

## Privacy

appTutorial only ever captures the **active window**, blocks sensitive apps, shows a capture
indicator with a pause control, and never writes screenshots or prompts to disk or
telemetry. See SPEC.md §10.
