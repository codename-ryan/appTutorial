import pytest

from apptutorial.hotkey import parse_hotkey

_MOD_ALT = 0x0001
_MOD_CONTROL = 0x0002
_MOD_SHIFT = 0x0004
_MOD_NOREPEAT = 0x4000


def test_parse_ctrl_alt_letter():
    mods, vk = parse_hotkey("ctrl+alt+t")
    assert vk == ord("T")
    assert mods & _MOD_CONTROL
    assert mods & _MOD_ALT
    assert mods & _MOD_NOREPEAT
    assert not (mods & _MOD_SHIFT)


def test_parse_function_key():
    mods, vk = parse_hotkey("F8")
    assert vk == 0x77  # VK_F8
    assert mods & _MOD_NOREPEAT


def test_parse_is_case_insensitive():
    assert parse_hotkey("Ctrl+Alt+T") == parse_hotkey("ctrl+alt+t")


def test_parse_requires_a_non_modifier_key():
    with pytest.raises(ValueError):
        parse_hotkey("ctrl+shift")


def test_parse_rejects_multiple_non_modifier_keys():
    with pytest.raises(ValueError):
        parse_hotkey("ctrl+a+b")
