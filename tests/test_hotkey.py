from apptutorial.hotkey import to_pynput_hotkey


def test_basic_combo():
    assert to_pynput_hotkey("ctrl+alt+h") == "<ctrl>+<alt>+h"


def test_aliases_and_case():
    assert to_pynput_hotkey("Win+Shift+S") == "<cmd>+<shift>+s"
    assert to_pynput_hotkey("Control+K") == "<ctrl>+k"


def test_single_key():
    assert to_pynput_hotkey("f8") == "f8"
