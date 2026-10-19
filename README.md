# appTutorial

An AI-powered, on-screen software tutor for **Windows**, running on a **local open-weight
vision model** (no cloud AI, no API key). Press a hotkey on a confusing app (Excel, an IDE, a
web app) and appTutorial captures the active window, identifies the app and your intent, and
walks you through tasks step by step — verifying each step against your live screen and
highlighting where to focus.

> Status: v1 built (Excel is the deeply-tested app). See **SPEC.md** for the full spec.

## How it works

1. **Hotkey** (default `Ctrl+Shift+T`) over the app you want help with.
2. An **open-weight vision model** (default: Qwen2.5-VL via local Ollama) identifies the app and
   suggests tutorials; pick one or type your own goal.
3. The model plans the steps; you get **one step at a time** with a see-through **highlight** on
   exactly where to act.
4. Each step is **verified automatically**: deterministic local checks first (Excel cell state
   via its COM object model, control state via UI Automation — fast, free, exact), with the
   vision model as a fallback for visual steps.
5. When a step is done, a green **Next** button appears — you confirm and move on. Back and
   manual Next always work.

## Quick start

First install [Ollama](https://ollama.com) and pull a vision model:

```powershell
ollama pull qwen2.5vl          # vision model; alternatives: llama3.2-vision, minicpm-v
```

Then set up appTutorial:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env          # defaults point at local Ollama; edit only to override
python -m apptutorial.app       # launches the tray app
```

Verify everything is wired up without starting the UI loop:

```powershell
python -m apptutorial.app --check
```

Look for the **green square** in the system tray (it may be under the `^` "show hidden icons"
arrow). Right-click it for the menu, or just press the hotkey over the app you want help with.
Set `APPTUTORIAL_DEBUG=1` to print step-by-step diagnostics to the terminal.

## AI backend

The app uses an **open-weight vision model** over an OpenAI-compatible API — a **local Ollama**
server by default, so no cloud AI and no API key. The `openai` pip package is only the HTTP
client; it talks to `http://localhost:11434` (your Ollama), not to OpenAI. To use a different
model or a hosted open-weight provider, set `OPENWEIGHT_*` in `.env`. See **AGENTS.md** for setup.

## Docs

- **SPEC.md** — full product specification and architecture.
- **AGENTS.md** — working guide, stack, conventions, invariants.

## Privacy

appTutorial only ever captures the **active window**, blocks sensitive apps, shows a capture
indicator with a pause control, and never writes screenshots or prompts to disk or telemetry.
With the default local model, screenshots never leave your machine at all. See SPEC.md §10.
