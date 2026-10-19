"""Excel state via the Excel COM automation object - authoritative and exact.

For the v1 target app, reading Excel's own object model is far more reliable than UI Automation
or vision for cell state: the selected range and a cell's value/formula come straight from
Excel. Used by the local step checker for 'cell_selected' / 'cell_value'. Every function
returns None whenever Excel isn't reachable - not running, busy in cell-edit mode (COM rejects
calls then), Excel Online, or COM blocked - so the caller falls back to UIA/vision.

COM must be initialized per worker thread, so each call does a balanced CoInitialize/
CoUninitialize. Calls are small (one property read) and safe to run on the watch cadence.
"""

from __future__ import annotations


def _normalize_addr(addr: str | None) -> str:
    return (addr or "").replace("$", "").strip().upper()


def selection_address() -> str | None:
    """The selected cell/range as 'B5' or 'B5:D10', or None if Excel isn't reachable."""
    try:
        import pythoncom
        import win32com.client
    except Exception:
        return None

    pythoncom.CoInitialize()
    try:
        app = win32com.client.GetActiveObject("Excel.Application")
        return _normalize_addr(app.Selection.Address) or None
    except Exception:
        return None
    finally:
        pythoncom.CoUninitialize()


def cell_text(ref: str) -> tuple[str, str] | None:
    """Return (value, formula) of a cell as strings, or None if Excel isn't reachable."""
    if not ref:
        return None
    try:
        import pythoncom
        import win32com.client
    except Exception:
        return None

    pythoncom.CoInitialize()
    try:
        app = win32com.client.GetActiveObject("Excel.Application")
        cell = app.Range(ref)
        value = cell.Value
        formula = cell.Formula
        return (
            "" if value is None else str(value),
            "" if formula is None else str(formula),
        )
    except Exception:
        return None
    finally:
        pythoncom.CoUninitialize()
