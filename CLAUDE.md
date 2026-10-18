# CLAUDE.md

Guidance for working in this repository. See **SPEC.md** for the full product spec.

## What this is

appTutorial is an AI-powered, on-screen software tutor for **Windows**. A hotkey captures
the active window; Claude identifies the app and the user's intent and guides them through
tasks step by step in a side panel, verifying each step against the live screen. v1 target
app: **Microsoft Excel**.

## Stack

- **Language:** Python 3.11+
- **UI:** PySide6 (Qt) — tray, capture indicator/pause, tutorial menu, step side panel,
  see-through highlight overlay
- **Windows integration:** `pywin32` (active window, process, bounds, DPI; `win32com`/
  `pythoncom` for the Excel COM object model), `psutil` (process name), `mss` (screenshot),
  `uiautomation` (UI Automation element tree/bounds/state)
- **Screen-change detection:** Pillow + a perceptual average-hash over the target region
- **AI:** official `anthropic` Python SDK
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
pip install -e ".[dev]"          # once pyproject.toml exists
copy .env.example .env           # then put your key in .env
```

### Anthropic API key (required)

This app calls the Claude API directly, which needs an **Anthropic Console** key with
billing — a Claude **Pro/Max subscription does not grant API access**.

1. Go to <https://console.anthropic.com> and sign in / sign up.
2. Add a payment method under **Billing**.
3. Create a key under **API keys**.
4. Put it in `.env` as `ANTHROPIC_API_KEY=sk-ant-...` (the SDK reads it automatically).

Never commit `.env` or hardcode the key.

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

- **Sonnet 5** (`claude-sonnet-5`): app identification, tutorial planning, answering
  questions. Vision + structured output; adaptive thinking on (`thinking={"type":"adaptive"}`).
- **Haiku 4.5** (`claude-haiku-4-5`): the fast step-verification check — the **fallback** when
  a step can't be checked deterministically. Vision + structured output; **no** thinking,
  small `max_tokens`, for speed/cost.
- Use the **exact** model ID strings above — never append date suffixes, never substitute a
  different model. These two are a deliberate product choice (capable model for
  understanding, fast model for the tight loop); don't "upgrade" them without being asked.
- **Hybrid verification (local-first):** prefer a deterministic local check over an AI call.
  The planner tags each step with a `StepCheck` (`ai/schemas.py`); `accessibility/
  local_check.py` evaluates it via UIA (control state) or Excel COM (`excel_com.py`: cell
  selection/value). Only `visual` steps — or local checks that come back undetermined — call
  Haiku. Keep this order; don't route checkable steps through the model.
- **Structured outputs:** every model call uses a Pydantic model via
  `client.messages.parse(..., output_format=Model)` → `response.parsed_output`. Define the
  models in `ai/schemas.py` (see SPEC.md §8.1 for the shapes).
- **Vision:** send the active-window screenshot as a base64 image content block.
- Route every AI call through `ai/client.py` so telemetry is recorded in one place. Local
  (UIA/COM) checks are free and are **not** logged as AI calls.

## Non-negotiable invariants

- **Privacy:** capture **only the active window**, never the full screen or background
  windows. Honor the sensitive-app **denylist** (auto-disable capture). Always show the
  **capture indicator** and keep **pause** working. Screenshots/prompts are held in memory,
  sent only to the Anthropic API, and **never** written to disk, logs, or telemetry/Sentry.
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
  (local UIA/Excel-COM checks first, Haiku vision fallback), **green manual confirm** per step,
  and a **see-through highlight overlay** on the current target. UIA grounds the models;
  Excel COM reads exact cell state.
- **Phase 2+:** the 5 per-step help buttons + free-text box, recap cards, Sentry adapter,
  sensitive-field redaction, project library, collaboration tutorials, Android Studio, macOS
  backend. Don't pull these into v1 without being asked.
