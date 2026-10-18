# appTutorial

An AI-powered, on-screen software tutor for **Windows**. Press a hotkey on a confusing app
(Excel, an IDE, a web app) and appTutorial captures the active window, uses Claude to
identify the app and your intent, and walks you through tasks step by step — verifying each
step against your live screen and highlighting where to focus.

> Status: v1 built (Excel is the deeply-tested app). See **SPEC.md** for the full spec.

## How it works

1. **Hotkey** (default `Ctrl+Shift+T`) over the app you want help with.
2. Claude **Sonnet 5** identifies the app and suggests tutorials; pick one or type your own goal.
3. Claude **Sonnet 5** plans the steps; you get **one step at a time** with a see-through
   **highlight** on exactly where to act.
4. Each step is **verified automatically**: deterministic local checks first (Excel cell state
   via its COM object model, control state via UI Automation — fast, free, exact), with Claude
   **Haiku 4.5** vision as a fallback for visual steps.
5. When a step is done, a green **Next** button appears — you confirm and move on. Back and
   manual Next always work.

## Quick start

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env          # then add your Anthropic Console API key
python -m apptutorial.app       # launches the tray app
```

Verify everything is wired up without starting the UI loop:

```powershell
python -m apptutorial.app --check
```

Look for the **green square** in the system tray (it may be under the `^` "show hidden icons"
arrow). Right-click it for the menu, or just press the hotkey over the app you want help with.
Set `APPTUTORIAL_DEBUG=1` to print step-by-step diagnostics to the terminal.

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
