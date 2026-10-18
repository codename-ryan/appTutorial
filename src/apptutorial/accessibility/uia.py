"""Windows UI Automation grounding: element names, control types, and pixel bounds.

Reads a compact summary of the active window's interactive elements (ribbon tabs, buttons,
menus) and feeds the names to the models so identification/planning/verification are grounded
in real UI chrome - not guesses from the screenshot alone (SPEC.md §7).

Runs off the UI thread, so it initializes COM for its worker thread. Only UI-chrome control
types are collected (not document/cell text), which keeps it focused and avoids pulling user
content into the summary. Coverage varies by app; any failure degrades to an empty list.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Interactive / chrome control types worth surfacing to the model. Deliberately excludes
# TextControl/EditControl/ListItemControl so document and cell content isn't collected.
_USEFUL_TYPES = frozenset(
    {
        "ButtonControl",
        "SplitButtonControl",
        "TabItemControl",
        "MenuItemControl",
        "CheckBoxControl",
        "RadioButtonControl",
        "ComboBoxControl",
        "ToolBarControl",
        "HyperlinkControl",
        "TreeItemControl",
    }
)

# Content containers we never descend into - their subtrees are huge document/cell content
# (e.g. Excel's cell grid), which would blow the visit budget before reaching real chrome.
_SKIP_DESCENT = frozenset({"DataGridControl", "TableControl", "DocumentControl"})


@dataclass(frozen=True)
class UIElement:
    name: str
    control_type: str
    left: int
    top: int
    width: int
    height: int


def is_meaningful_name(name: str) -> bool:
    """True if the name has real text (not empty, whitespace, or only icon-font glyphs)."""
    return bool(name) and any(ch.isalnum() for ch in name)


def summarize_active_window(
    hwnd: int, *, max_elements: int = 80, max_depth: int = 9, max_visit: int = 600
) -> list[UIElement]:
    """Return a bounded list of meaningful UI elements for the given window.

    Safe to call from a worker thread (initializes COM). Returns ``[]`` on any failure or if
    the app exposes no usable accessibility tree - grounding is best-effort, never required.
    """
    try:
        import uiautomation as auto
    except Exception:
        return []

    # Stop the library from dropping an @AutomationLog.txt file in the working directory.
    try:
        auto.Logger.SetLogFile(os.devnull)
    except Exception:
        pass

    elements: list[UIElement] = []
    try:
        # UIAutomationInitializerInThread sets up COM + a thread-local automation client;
        # it's required for UIA from a worker thread and gives full tree coverage
        # (including XAML/UWP windows that a bare CoInitialize misses).
        with auto.UIAutomationInitializerInThread():
            root = auto.ControlFromHandle(hwnd)
            if root is not None:
                _walk(root, 0, max_depth, max_elements, max_visit, {"visited": 0}, elements)
    except Exception:
        return elements  # partial result is fine; never raise
    return elements


def _walk(control, depth, max_depth, max_elements, max_visit, state, out) -> None:
    if depth > max_depth or len(out) >= max_elements or state["visited"] >= max_visit:
        return
    try:
        children = control.GetChildren()
    except Exception:
        return
    for child in children:
        if len(out) >= max_elements or state["visited"] >= max_visit:
            return
        state["visited"] += 1
        try:
            name = (child.Name or "").strip()
            control_type = child.ControlTypeName
        except Exception:
            continue
        if control_type in _USEFUL_TYPES and is_meaningful_name(name):
            try:
                rect = child.BoundingRectangle
                out.append(
                    UIElement(name, control_type, rect.left, rect.top, rect.width(), rect.height())
                )
            except Exception:
                out.append(UIElement(name, control_type, 0, 0, 0, 0))
        if control_type not in _SKIP_DESCENT:
            _walk(child, depth + 1, max_depth, max_elements, max_visit, state, out)


def find_element_rect(
    hwnd: int,
    name_hint: str,
    role_hint: str | None = None,
    *,
    max_depth: int = 9,
    max_visit: int = 800,
) -> tuple[int, int, int, int] | None:
    """Best-effort screen-pixel box (left, top, width, height) of the element a step targets.

    Matches the first element whose accessibility name matches ``name_hint`` (and role, if
    given), so change-detection and verification can focus on that specific control. Returns
    ``None`` on any failure - callers fall back to tracking the whole window.
    """
    if not name_hint:
        return None
    try:
        import uiautomation as auto
    except Exception:
        return None
    try:
        auto.Logger.SetLogFile(os.devnull)
    except Exception:
        pass

    target = name_hint.strip().lower()
    role = (role_hint or "").strip().lower().removesuffix("control")
    try:
        with auto.UIAutomationInitializerInThread():
            root = auto.ControlFromHandle(hwnd)
            if root is None:
                return None
            return _search_rect(root, 0, max_depth, max_visit, {"visited": 0}, target, role)
    except Exception:
        return None


def _search_rect(control, depth, max_depth, max_visit, state, target, role):
    if depth > max_depth or state["visited"] >= max_visit:
        return None
    try:
        children = control.GetChildren()
    except Exception:
        return None
    for child in children:
        if state["visited"] >= max_visit:
            return None
        state["visited"] += 1
        try:
            name = (child.Name or "").strip().lower()
            control_type = child.ControlTypeName
        except Exception:
            continue
        ctype = control_type.removesuffix("Control").lower()
        if name and (name == target or target in name or name in target):
            if not role or role in ctype or ctype in role:
                try:
                    rect = child.BoundingRectangle
                    if rect.width() > 0 and rect.height() > 0:
                        return (rect.left, rect.top, rect.width(), rect.height())
                except Exception:
                    pass
        if control_type not in _SKIP_DESCENT:
            found = _search_rect(child, depth + 1, max_depth, max_visit, state, target, role)
            if found:
                return found
    return None


def format_elements(elements: list[UIElement], limit: int = 50) -> str:
    """Compact text for the model prompt, e.g. ``- [TabItem] Home``."""
    if not elements:
        return "(no accessibility data available for this window)"
    return "\n".join(
        f"- [{e.control_type.removesuffix('Control')}] {e.name}" for e in elements[:limit]
    )
