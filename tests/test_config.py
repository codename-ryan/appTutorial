from apptutorial.config import DEFAULT_DENYLIST, load_config


def test_load_config_defaults(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("APPTUTORIAL_HOTKEY", raising=False)
    monkeypatch.delenv("APPTUTORIAL_DENYLIST", raising=False)

    cfg = load_config()

    assert cfg.hotkey == "ctrl+alt+h"
    assert cfg.denylist == DEFAULT_DENYLIST
    assert cfg.identify_model == "claude-sonnet-5"
    assert cfg.verify_model == "claude-haiku-4-5"


def test_denylist_override(monkeypatch):
    monkeypatch.setenv("APPTUTORIAL_DENYLIST", "Foo.exe, Bar.EXE")

    cfg = load_config()

    assert cfg.denylist == ("foo.exe", "bar.exe")
