# appTutorial — Specification

**An AI-powered, on-screen software tutor for Windows.**

Press a hotkey on any confusing app (Excel, an IDE, a web app). appTutorial captures
the active window, uses Claude to figure out what the app is and what you're trying to
do, and walks you through it step by step in a side panel — verifying each step against
what's actually on your screen, so the guidance always matches the version in front of
you.

- **Status:** v1 implemented (M0–M6): capture → identify → menu → plan → guided steps with
  hybrid (local + AI) verification and a highlight overlay. Excel is the deeply-tested app.
- **Last updated:** 2026-10-18
- **Owner:** @codename-ryan

---

## 1. Problem & vision

Powerful software (Excel, Android Studio, Blender, DAWs, enterprise tools) buries huge
capability behind dense toolbars and menus. New users don't know what the buttons do,
what the app is *for*, or how to accomplish a specific goal. Written tutorials and videos
go stale the moment the UI changes and can't see *your* screen.

appTutorial is a live, screen-aware tutor. It looks at the actual window, identifies the
software and the user's apparent intent, and delivers interactive, step-by-step guidance
that is always grounded in the current screenshot — never a remembered or outdated UI.

### Guiding principles

1. **Ground everything in the live screen.** Never describe menus or steps from an older
   version. Every instruction is derived from, or verified against, the current screenshot
   and accessibility tree. Never rely on on-screen text that could be misleading or work
   against the user's stated goal.
2. **Privacy by default.** Only the focused window is ever captured. Sensitive apps are
   blocked. Screenshots and prompts are never written to logs or external telemetry. A
   capture indicator and pause control are always available.
3. **Teach, don't just click.** The goal is for the user to learn the software, not to be
   driven blindly. Steps explain *what* and (on request) *why*.
4. **Right model for the job.** A capable model for understanding and planning; a fast,
   cheap model for the tight "did they do it yet?" loop.

---

## 2. Goals & non-goals

### Goals (overall product)
- Identify the active application and the user's likely intent from a screenshot + process name.
- Offer a tutorial menu: a basic tour, feature tutorials, project tutorials, or a user-typed goal.
- Deliver guided, one-step-at-a-time instructions in a side panel.
- Verify step completion automatically: deterministic local checks (Excel COM / UIA) first,
  with a fast vision model as fallback for visual steps.
- Highlight where to focus with a see-through, click-through overlay aligned to the real UI.
- Answer free-text questions and offer per-step help: Simpler / More detail / Why? / I'm
  stuck / What can I do here (phase 2).
- Log model/token/latency telemetry locally, with an optional Sentry adapter — never
  screenshots or prompt bodies.

### Non-goals
- **Not** an automation/RPA tool. appTutorial never clicks or types for the user; it guides.
- **Not** a screen recorder or background surveillance tool. Capture is explicit, scoped to
  the active window, and indicated.
- **Not** cross-platform in v1. The accessibility-grounded highlighting relies on Windows UI
  Automation. The capture/accessibility layer is kept behind an interface so a macOS backend
  could be added later, but v1 is Windows-only.

---

## 3. Scope

### v1 (this build)
1. Global hotkey to start a session on the active window.
2. Capture pipeline: active window handle, process name, window bounds, per-monitor DPI
   scale, and an active-window-only screenshot normalized for scale factor.
3. Privacy: active-window-only capture, configurable sensitive-app denylist (capture
   auto-disables), always-visible capture indicator, and a pause control.
4. App identification via **Claude Sonnet 5** → structured JSON (app, category, on-screen
   context, suggested tutorials).
5. Tutorial menu: basic tour / feature tutorials / project tutorials / type-your-own-goal.
6. Tutorial planning via **Claude Sonnet 5** → structured JSON steps (instruction, target
   description, "done" condition).
7. Step side panel: one step at a time (instruction + what "done" looks like), Next/Back,
   session progress.
8. Screen-change detection (local perceptual average-hash over the target region) gating AI
   verification so frames are never streamed to the API.
9. **Hybrid step verification.** For steps whose completion is a well-defined state, a
   deterministic local check runs every ~0.8s with **no AI call**: Excel cell state
   (selection, value/formula) via the **Excel COM** object model, and control state (tab
   selected, dialog/pane open, checkbox on, field focused) via **UIA**. Visual steps — and
   any local check that can't be determined — fall back to **Claude Haiku 4.5** vision
   verification (full screenshot + a close-up of the target + a UIA summary). A detected step
   is confirmed by the user with a green **Next** button (no silent auto-advance); Back and
   manual Next always work.
10. UI Automation (UIA) **grounding**: element names/roles/bounds are read and passed to the
    models to improve identification, planning, and verification accuracy.
11. **See-through highlight overlay** framing the current step's target — a cell (via Excel
    COM point→pixel conversion) or a control (via UIA bounds). Click-through, never steals
    focus, excluded from screen capture, and placed at exact physical pixels via Win32
    `SetWindowPos` (bypasses Qt's DPI transform). Cell highlights re-read position to **track
    scrolling** and hide when the cell leaves the visible grid.
12. Local JSONL telemetry: per-call model, token usage, latency, step index. No screenshots,
    no prompt bodies.
13. First deeply-tested target app: **Microsoft Excel** (others still work generically).

### Phase 2
- Per-step help buttons (**Simpler / More detail / Why? / I'm stuck / What can I do here**)
  and the free-text question box.
- **Recap card** at the end of a tutorial.
- Sentry adapter wired to the existing telemetry events.
- Sensitive-field redaction (blur password/secure fields via UIA before sending).

### Phase 3+
- Saved **project-tutorial library** and resumable projects.
- **Collaboration / Git tutorials** (e.g. working with partners in Android Studio for FTC).
- Deep support for additional apps (Android Studio / JetBrains, browsers, Blender, …).
- Optional macOS backend behind the capture/accessibility interface.

---

## 4. Users & core use cases

- **The confused newcomer:** opens Excel/Android Studio for the first time, has no idea
  where to start. Wants "what is this and how do I use it."
- **The goal-driven user:** knows what they want ("record a macro," "set up FTC robot code,"
  "do a VLOOKUP") and wants to be walked through it in their actual app.
- **The stuck intermediate:** mid-task, hits a wall, wants a specific feature explained
  against what's currently on screen.

---

## 5. Architecture overview

```
                         ┌─────────────────────────────────────────────┐
  Hotkey ──────────────▶ │  Session Orchestrator (app.py)              │
                         │  owns the state machine + session lifecycle  │
                         └───┬───────────────┬───────────────┬─────────┘
                             │               │               │
             ┌───────────────▼──┐   ┌────────▼────────┐   ┌──▼───────────────┐
             │ Capture layer    │   │ AI layer        │   │ UI layer (PySide6)│
             │ (Windows)        │   │ (Anthropic)     │   │                   │
             │ • active window  │   │ • identify      │   │ • system tray     │
             │ • process name   │   │   (Sonnet 5)    │   │ • capture indicator│
             │ • bounds + DPI   │   │ • plan          │   │   + pause         │
             │ • screenshot     │   │   (Sonnet 5)    │   │ • tutorial menu   │
             │ • change detect  │   │ • verify        │   │ • step side panel │
             └───────┬──────────┘   │   (Haiku 4.5)   │   └───────────────────┘
                     │              └────────┬────────┘
             ┌───────▼──────────┐           │
             │ Accessibility    │           ▼
             │ (UI Automation)  │   ┌─────────────────┐
             │ • element tree   │   │ Telemetry        │
             │ • names + bounds │   │ • JSONL (local)  │
             └──────────────────┘   │ • Sentry (later) │
                     ▲              └─────────────────┘
             ┌───────┴──────────┐
             │ Privacy gate     │
             │ • denylist       │
             │ • active-win only│
             └──────────────────┘
```

### Planned repository layout
```
appTutorial/
  SPEC.md
  CLAUDE.md
  README.md
  pyproject.toml            # deps + tooling (ruff, pytest)
  .env.example              # ANTHROPIC_API_KEY=...
  .gitignore
  src/apptutorial/
    app.py                  # entry point, tray, hotkey, orchestrator/state machine
    config.py               # settings, denylist, API key loading, hotkey binding
    capture/
      window.py             # active window, process name, bounds, DPI (pywin32)
      screenshot.py         # active-window screenshot (mss/PrintWindow) + scale correction
      change_detector.py    # perceptual hash / frame diff → "screen changed?"
      backend.py            # CaptureBackend interface (Windows impl now; Mac later)
    accessibility/
      uia.py                # UI Automation element tree, names/roles/bounds, element rect
      local_check.py        # deterministic step checks (UIA + Excel COM), no AI
      excel_com.py          # Excel object model: selection, cell value/formula, cell rect
    ai/
      client.py             # Anthropic client wrapper (+ telemetry hooks)
      schemas.py            # Pydantic models for structured outputs (incl. StepCheck)
      identify.py           # app identification (Sonnet 5)
      plan.py               # tutorial planning (Sonnet 5)
      verify.py             # step verification fallback (Haiku 4.5)
    ui/
      tray.py               # tray icon, capture indicator, pause toggle
      menu.py               # tutorial menu
      session_window.py     # floating card: analyzing / menu / step panel host
      panel.py              # step side panel (one step, Back / Why? / Next, green confirm)
      overlay.py            # see-through, click-through highlight overlay
    privacy/
      denylist.py           # sensitive-app blocklist + checks
    telemetry/
      logger.py             # local JSONL events (model/tokens/latency/step)
  tests/
    ...
```

---

## 6. Capture pipeline

1. **Hotkey** (configurable; default `Ctrl+Shift+T`) registered globally via the Win32
   `RegisterHotKey` API, so the OS routes it to appTutorial and suppresses it from the
   foreground app (it won't also trigger the app's own shortcut). `Ctrl+Alt+*` is avoided
   because many keyboard layouts treat Ctrl+Alt as AltGr, so those hotkeys register but
   never fire.
2. **Active window** via `GetForegroundWindow`; **process name** via
   `GetWindowThreadProcessId` + `psutil`; **window rect** via `GetWindowRect`.
3. **DPI / scale factor:** the app is per-monitor DPI-aware. Window bounds and screenshots
   are captured in physical pixels. Element/cell target boxes (UIA bounds, Excel COM) are also
   physical, and the highlight overlay is positioned at those exact physical pixels via Win32
   `SetWindowPos` — deliberately bypassing Qt's logical-coordinate/DPI transform, which is the
   single most common source of misaligned overlays under mixed-DPI / multi-monitor setups.
4. **Screenshot:** only the active window region is captured (never the full desktop or
   background windows), via `mss` or `PrintWindow`, encoded to PNG → base64 for the vision
   call. Held in memory only; never written to disk or logs.
5. **Change detection:** a cheap local signal (downscaled perceptual hash / frame diff over
   the window region) runs on a timer. The expensive vision verification call fires **only**
   when the screen meaningfully changes — frames are never streamed continuously to the API
   (cost + privacy). A debounce prevents mid-animation false positives.

---

## 7. Accessibility (UI Automation) grounding

Claude's vision is strong at *understanding* a screen but unreliable at returning
pixel-perfect bounding boxes for small UI elements. Windows UI Automation exposes the
**exact** rectangle and name/role of real UI elements. The hybrid strategy:

- **Grounding (v1):** read the UIA element tree for the active window (names, control types,
  bounds) and pass a compact summary to the models. This grounds identification ("the ribbon
  has Formulas/Data/Review tabs"), planning ("target: Formulas tab"), and verification ("is
  the Formulas tab now selected?").
- **Deterministic verification (v1):** control state is read straight from UIA
  (`SelectionItemPattern.IsSelected`, `TogglePattern.ToggleState`, `ValuePattern.Value`,
  focus) so a step like "the Developer tab is selected" is checked exactly, with no AI call.
- **Highlight overlay (v1):** the overlay draws its frame at the UIA-reported bounds of the
  target element. For Excel cells (which live in a skipped grid subtree), bounds come from
  **Excel COM** (`Window.PointsToScreenPixelsX/Y`) instead.

**Excel COM:** for the v1 target app, cell state is read from Excel's own object model
(`Selection.Address`, `Range(ref).Value/.Formula`, cell screen rect) — exact and reliable
where UIA/vision are weak. Returns nothing when Excel isn't reachable (not running, mid cell
edit, Excel Online), so verification falls back to UIA/vision.

UIA coverage by app: Excel/Office — excellent; browsers — partial (web content via
UIA/IA2); Android Studio (JetBrains/Java) — partial. This is why the COM path (Excel) and
vision fallback matter.

---

## 8. AI integration

**SDK:** official `anthropic` Python package. **Auth:** `ANTHROPIC_API_KEY` env var (an
Anthropic **Console** key with billing; a Claude Pro/Max subscription does not grant API
access — see CLAUDE.md for setup).

| Role | Model | ID | Notes |
|---|---|---|---|
| Identify app, plan tutorials, answer questions | Claude Sonnet 5 | `claude-sonnet-5` | Vision + structured output; adaptive thinking on. |
| Fast "did they do the step?" check | Claude Haiku 4.5 | `claude-haiku-4-5` | Vision + structured output; no thinking, small `max_tokens`, for speed/cost. |

- **Vision:** the active-window screenshot is sent as a base64 image content block.
- **Structured outputs:** every call uses JSON-schema-constrained output via Pydantic models
  and `client.messages.parse(..., output_format=Model)` → `response.parsed_output`. This
  guarantees machine-readable results (step = instruction + target + "done" definition).
- **Hybrid verification (local-first):** the planner also emits a machine-checkable `check`
  per step (see §8.1). When the completion state is well-defined (a cell selected/filled, a
  tab selected, a dialog open, a box checked), the tight loop verifies it **locally** (Excel
  COM / UIA) with no API call — faster, free, and exact. Only `visual` steps, or local checks
  that can't be determined, reach the Haiku vision call. This keeps AI usage to planning plus
  the genuinely visual checks.
- **Streaming:** user-facing text (e.g. step explanations) streams to the panel for
  responsiveness; the expensive vision call still fires only on a detected screen change.
- **Prompt caching (phase 2 optimization):** the large, stable system prompts for
  identification/verification are cache-friendly; volatile content (screenshot, step) goes
  last.
- **Privacy:** screenshots are sent to the Anthropic API only for the analysis that is the
  core function of the product. They are **not** persisted to disk and **never** included in
  telemetry or Sentry.

### 8.1 Structured output schemas (Pydantic)

**AppIdentification** (Sonnet 5):
```jsonc
{
  "app_name": "Microsoft Excel",
  "app_category": "spreadsheet",
  "confidence": 0.0,                     // 0–1
  "detected_version_hint": null,          // only if visible on screen; never assumed
  "current_context": "Blank workbook, Home tab active",
  "visible_capabilities": ["ribbon tabs", "formula bar", "cell grid"],
  "suggested_tutorials": [
    { "id": "basic-tour", "title": "What is Excel and how to use it", "kind": "tour" },
    { "id": "macros",     "title": "Record and run a macro",          "kind": "feature" }
  ]
}
```

**TutorialPlan** (Sonnet 5):
```jsonc
{
  "goal": "Record a simple macro",
  "app_name": "Microsoft Excel",
  "steps": [
    {
      "index": 0,
      "instruction": "Open the Developer tab, then click \"Record Macro\".",
      "rationale": "The Developer tab holds macro tools; recording captures your actions.",
      "target": {
        "description": "Record Macro button on the Developer tab",
        "uia_name_hint": "Record Macro",
        "uia_role_hint": "Button"
      },
      "done_when": "The \"Record Macro\" dialog is open",
      "done_signals": ["a dialog titled Record Macro is visible"],
      "check": { "kind": "element_present", "target": "Record Macro", "expected": null }
    }
  ]
}
```

**StepCheck** (part of each step; drives local, no-AI verification):
```jsonc
{
  // kind: cell_selected | cell_value | element_selected | element_present |
  //       element_focused | checkbox_checked | value_equals | visual
  "kind": "cell_value",
  "target": "A11",            // cell ref (cell_*) or element name (element_*/checkbox/value)
  "expected": "=SUM(A1:A10)"  // value/formula for cell_value & value_equals; else null
}
```
`cell_selected`/`cell_value` are checked via Excel COM; the element/checkbox/value kinds via
UIA; `visual` (or any undetermined local check) falls back to the Haiku vision check.

**StepVerification** (Haiku 4.5):
```jsonc
{
  "status": "done",                 // done | not_done | unclear | off_track
  "confidence": 0.0,                // 0–1
  "observation": "The Record Macro dialog is now open",
  "hint": null                       // a nudge when not_done / off_track
}
```

---

## 9. Session state machine (v1)

```
IDLE
  └─(hotkey)→ CHECK_PRIVACY
        ├─(app on denylist)→ BLOCKED → IDLE
        └─(allowed)→ CAPTURE → IDENTIFYING (Sonnet 5)
                        └→ MENU
                             └─(pick tutorial / type goal)→ PLANNING (Sonnet 5)
                                   └→ GUIDING(step i)  [highlight overlay on target]
                                        ├─ local check (Excel COM / UIA, every ~0.8s, no AI)
                                        │     ├─ done → AWAIT_CONFIRM (green Next)
                                        │     ├─ not done → keep watching
                                        │     └─ undetermined (xN) → AI fallback ↓
                                        ├─(screen change / heartbeat, visual steps)→ VERIFYING (Haiku 4.5)
                                        │     ├─ done → AWAIT_CONFIRM (green Next)
                                        │     ├─ not_done/off_track → show hint, stay
                                        │     └─ unclear → wait / allow manual advance
                                        └─(pause)→ PAUSED → (resume) GUIDING(step i)
AWAIT_CONFIRM ─(user clicks Next)→ GUIDING(step i+1) | COMPLETE
COMPLETE → "Back to tutorials" → MENU        (recap card = phase 2)
PAUSED: all capture + API calls halted until resumed.
```

Manual override: the user can always advance/retreat steps regardless of verification, and
can pause at any time.

---

## 10. Privacy model

- **Active-window-only.** Only the focused window is captured. The full desktop and
  background windows are never read.
- **Denylist.** A configurable list of sensitive apps (password managers, banking apps,
  etc.). When the active app matches, capture auto-disables and the user is told.
- **Capture indicator + pause.** While a session is active, a clear indicator is always
  visible; a pause control immediately halts all capture and API activity.
- **No persistence of screen content.** Screenshots/prompts are held in memory only, sent to
  the Anthropic API for analysis, and never written to disk, logs, or telemetry/Sentry.
- **Transparency.** The screenshot does leave the machine — it goes to the Anthropic API,
  which is inherent to a vision-based tutor. This is stated plainly to the user; the privacy
  guarantees are about scope (active window only), control (denylist + pause), and
  non-persistence (never logged/stored).
- **Phase 2:** detect and blur password/secure fields (via UIA) before sending.

---

## 11. Telemetry

- **v1:** append-only local **JSONL** file. One event per API call:
  `{ ts, model, call_type, input_tokens, output_tokens, latency_ms, step_index, status }`.
  Never the screenshot, never prompt/response bodies.
- **Phase 2:** a thin Sentry adapter emits the same events as spans/breadcrumbs with
  `send_default_pii=False` and explicit scrubbing, so screenshots and prompt text never
  leave the machine via Sentry.

---

## 12. Key risks & mitigations

| Risk | Mitigation |
|---|---|
| Vision coordinates imprecise for small UI elements | Accessibility-first hybrid: UIA bounds + text anchors; vision only as fallback (phase 2 overlay). |
| UIA coverage varies by app | Target Excel first (strong UIA); vision fallback + text anchors for weak-coverage apps. |
| Stale UI guidance | Every step verified against the live screenshot; identification/planning grounded in current screen + UIA, never assumed versions. |
| API cost from frequent vision calls | Local change-detection gates verification; Haiku (cheap) for the tight loop; Sonnet only for ID/planning. |
| DPI / multi-monitor misalignment | Per-monitor DPI awareness handled centrally in the capture layer; scale-factor normalization. |
| Privacy exposure | Active-window-only capture, denylist, indicator + pause, no persistence, no screenshots in telemetry. |
| User has no API access | Pro/Max doesn't grant API access; setup steps for a Console key in CLAUDE.md. |

---

## 13. Open questions (to revisit)
- Default hotkey choice and conflict handling.
- Exact change-detection threshold / debounce timing (tune empirically).
- How aggressively to re-plan when the user diverges from the planned path.
- Initial contents of the sensitive-app denylist.
