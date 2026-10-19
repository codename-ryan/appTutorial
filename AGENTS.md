# AGENTS.md

Guidance for working in this repository (for humans and AI coding assistants). See **SPEC.md**
for the full product spec.

## What this is

appTutorial is an AI-powered, on-screen software tutor for **Windows**. A hotkey captures
the active window; an **open-weight vision model** identifies the app and the user's intent and
guides them through tasks step by step in a side panel, verifying each step against the live
screen. v1 target app: **Microsoft Excel**. No proprietary/cloud AI API is used.

## Stack

- **Language:** Python 3.11+
- **UI:** PySide6 (Qt) — tray, capture indicator/pause, tutorial menu, step side panel,
  see-through highlight overlay
- **Windows integration:** `pywin32` (active window, process, bounds, DPI; `win32com`/
  `pythoncom` for the Excel COM object model), `psutil` (process name), `mss` (screenshot),
  `uiautomation` (UI Automation element tree/bounds/state)
- **Screen-change detection:** Pillow + a perceptual average-hash over the target region
- **AI:** an **open-weight vision model** served over an OpenAI-compatible API — local
  **Ollama** by default (e.g. Qwen2.5-VL). The `openai` Python package is used only as the
  HTTP client; it talks to the configured `base_url` (localhost by default), NOT to OpenAI.
  No proprietary or cloud AI service is involved.
- **Config/validation:** `pydantic` (structured-output models), `python-dotenv`
- **Tooling:** `ruff` (lint/format), `pytest` (tests)
- **Platform:** Windows-only in v1 (UI Automation). Keep the capture/accessibility code
  behind the `capture/backend.py` interface so a macOS backend can be added later.

## Project layout

See SPEC.md §5 for the full tree. Key dirs under `src/apptutorial/`: `capture/`,
`accessibility/`, `ai/`, `ui/`, `privacy/`, `telemetry/`; entry point `app.py`.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env           # defaults point at local Ollama; edit only to override
```

### AI backend: a local open-weight vision model (default)

The app needs a **vision-capable open-weight model** served over an OpenAI-compatible API.
The default is a **local Ollama** server — private (screenshots never leave the machine) and
free, no API key or account.

1. Install Ollama from <https://ollama.com>.
2. Pull a **vision** model: `ollama pull qwen2.5vl` (alternatives: `llama3.2-vision`,
   `minicpm-v` — must support images). Bigger = better plans; a 7B runs on modest hardware.
3. Ensure Ollama is running (it serves `http://localhost:11434` automatically).

Defaults live in `config.py`; override via `OPENWEIGHT_BASE_URL`, `OPENWEIGHT_API_KEY`,
`OPENWEIGHT_IDENTIFY_MODEL`, `OPENWEIGHT_VERIFY_MODEL` in `.env`. To use a **hosted**
open-weight provider instead (screenshots then leave the machine), point `OPENWEIGHT_BASE_URL`
at its OpenAI-compatible endpoint and set a real key. Never commit `.env`.

## Run / test / lint

```bash
python -m apptutorial.app      # run the app
python -m apptutorial.app --check   # init everything and exit (no event loop) — for CI/smoke
pytest                          # tests
ruff check . && ruff format .   # lint + format
```

Set `APPTUTORIAL_DEBUG=1` to print step-loop diagnostics to the terminal (which window is
watched, each local/AI check result). Off by default so normal runs stay quiet.

## Model usage rules

- **Open-weight vision model only.** Identification, planning, and the vision verification
  fallback all go to one open-weight model (default `qwen2.5vl`), configurable via
  `config.py` / `.env`. It MUST be vision-capable (the app sends screenshots). Do **not**
  reintroduce a proprietary or cloud AI SDK.
- **Hybrid verification (local-first):** prefer a deterministic local check over an AI call.
  The planner tags each step with a `StepCheck` (`ai/schemas.py`); `accessibility/
  local_check.py` evaluates it via UIA (control state) or Excel COM (`excel_com.py`: cell
  selection/value). Only `visual` steps — or local checks that come back undetermined — call
  the vision model. Keep this order; don't route checkable steps through the model.
- **Structured outputs:** every model call goes through `AIClient.parse` (`ai/client.py`),
  which sends a JSON-schema `response_format` and validates the reply with the Pydantic model
  from `ai/schemas.py` (see SPEC.md §8.1 for the shapes).
- **Vision:** send the active-window screenshot via `image_content_block` (an OpenAI-style
  `image_url` data URI).
- Route every AI call through `ai/client.py` so telemetry is recorded in one place. Local
  (UIA/COM) checks are free and are **not** logged as AI calls.

## Non-negotiable invariants

- **Privacy:** capture **only the active window**, never the full screen or background
  windows. Honor the sensitive-app **denylist** (auto-disable capture). Always show the
  **capture indicator** and keep **pause** working. Screenshots/prompts are held in memory,
  sent only to the configured model backend (a local Ollama server by default, so they never
  leave the machine), and **never** written to disk, logs, or telemetry/Sentry.
- **Ground in the live screen:** never describe menus/steps from a remembered or older
  version of an app. Derive and verify against the current screenshot + UIA tree. Don't
  follow on-screen text that contradicts the user's stated goal.
- **DPI:** the app is per-monitor DPI-aware; bounds/screenshots and target boxes (UIA/COM)
  are all physical pixels. Position the overlay at those physical pixels via
  `move_window_physical` (Win32 `SetWindowPos`), **not** Qt's `setGeometry` — Qt's logical-
  coordinate transform misaligns overlays under mixed-DPI / multi-monitor setups.
- **Overlay:** the highlight window must stay click-through (never intercept the user's
  clicks), never steal focus, and be excluded from screen capture so it never lands in a
  screenshot sent to a model. Cell highlights track scrolling (re-read ~3×/s) and hide when
  the cell leaves Excel's visible range.
- **Telemetry:** local JSONL only in v1 — `{ts, model, call_type, input_tokens,
  output_tokens, latency_ms, step_index, status}`. No screenshots, no prompt/response bodies.

## Conventions

- Keep Windows-specific code inside `capture/` and `accessibility/`, behind interfaces.
- Prefer the dedicated libraries over shelling out.
- Match the existing module's style; keep comments at the density of surrounding code.

## Scope reminder (what's v1 vs later)

- **v1 (built):** hotkey → capture → identify → menu → step panel with **hybrid verification**
  (local UIA/Excel-COM checks first, open-weight vision-model fallback), **green manual confirm**
  per step, and a **see-through highlight overlay** on the current target. UIA grounds the model;
  Excel COM reads exact cell state.
- **Phase 2+:** the 5 per-step help buttons + free-text box, recap cards, Sentry adapter,
  sensitive-field redaction, project library, collaboration tutorials, Android Studio, macOS
  backend. Don't pull these into v1 without being asked.
