"""Deterministic step verification via UI Automation - no AI call.

For steps whose completion is a well-defined UI state (a tab selected, a dialog open, a cell
selected, a checkbox on), we read the live accessibility tree directly instead of sending a
screenshot to the model. This is faster, free, and far more reliable for subtle states - an
Excel cell selection is nearly invisible in a screenshot but is exact in the tree (the Name
Box holds the reference). ``evaluate_check`` returns True (done), False (not done), or None
(undetermined - the caller falls back to AI verification). See SPEC.md §8.
"""

from __future__ import annotations

import os

from apptutorial.accessibility.uia import _SKIP_DESCENT


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def cell_matches(value: str | None, expected: str | None) -> bool:
    """True if a Name Box value matches the expected cell/range (exact or anchor cell)."""
    current = _norm(value)
    want = _norm(expected)
    if not current or not want:
        return False
    return current == want or current.split(":")[0] == want


def evaluate_check(hwnd, kind, target, expected):
    """Return True (done), False (not done), or None (undetermined -> use AI verification)."""
    if not kind or kind == "visual":
        return None
    try:
        import uiautomation as auto
    except Exception:
        return None
    try:
        auto.Logger.SetLogFile(os.devnull)
    except Exception:
        pass

    try:
        with auto.UIAutomationInitializerInThread():
            root = auto.ControlFromHandle(hwnd)
            if root is None:
                return None
            if kind == "cell_selected":
                return _cell_selected(root, expected or target)
            if kind == "element_focused":
                return _is_focused(auto, target)
            if kind == "element_present":
                return None if not target else (_find(root, target) is not None)
            control = _find(root, target) if target else None
            if control is None:
                return None  # can't locate the element -> let the AI decide
            if kind == "element_selected":
                return _is_selected(control)
            if kind == "checkbox_checked":
                return _is_checked(auto, control)
            if kind == "value_equals":
                return _value_equals(control, expected)
    except Exception:
        return None
    return None


def _cell_selected(root, expected):
    if not expected:
        return None
    name_box = _find(root, "name box", role="edit") or _find(root, "name box")
    if name_box is None:
        return None
    try:
        value = name_box.GetValuePattern().Value
    except Exception:
        return None
    return cell_matches(value, expected)


def _is_selected(control):
    try:
        return bool(control.GetSelectionItemPattern().IsSelected)
    except Exception:
        return None


def _is_checked(auto, control):
    try:
        return control.GetTogglePattern().ToggleState == auto.ToggleState.On
    except Exception:
        return None


def _value_equals(control, expected):
    if expected is None:
        return None
    try:
        value = control.GetValuePattern().Value
    except Exception:
        return None
    return _norm(value) == _norm(expected)


def _is_focused(auto, target):
    if not target:
        return None
    try:
        focused = auto.GetFocusedControl()
    except Exception:
        return None
    name = _norm(focused.Name) if focused is not None else ""
    if not name:
        return None
    want = _norm(target)
    return name == want or want in name or name in want


def _find(root, name, role=None, *, max_depth=9, max_visit=800):
    if not name:
        return None
    target = _norm(name)
    role_norm = _norm(role).removesuffix("control")
    return _dfs(root, 0, max_depth, max_visit, {"visited": 0}, target, role_norm)


def _dfs(control, depth, max_depth, max_visit, state, target, role):
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
            name = _norm(child.Name)
            control_type = child.ControlTypeName
        except Exception:
            continue
        ctype = control_type.removesuffix("Control").lower()
        if name and (name == target or target in name or name in target):
            if not role or role in ctype or ctype in role:
                return child
        if control_type not in _SKIP_DESCENT:
            found = _dfs(child, depth + 1, max_depth, max_visit, state, target, role)
            if found is not None:
                return found
    return None
