from apptutorial.config import DEFAULT_DENYLIST, load_config


def test_load_config_defaults(monkeypatch):
    for var in (
        "OPENWEIGHT_BASE_URL",
        "OPENWEIGHT_IDENTIFY_MODEL",
        "OPENWEIGHT_VERIFY_MODEL",
        "APPTUTORIAL_HOTKEY",
        "APPTUTORIAL_DENYLIST",
    ):
        monkeypatch.delenv(var, raising=False)

    cfg = load_config()

    assert cfg.hotkey == "ctrl+shift+t"
    assert cfg.denylist == DEFAULT_DENYLIST
    assert cfg.openweight_base_url == "http://localhost:11434/v1"
    assert cfg.identify_model == "qwen2.5vl"
    assert cfg.backend_configured is True


def test_denylist_override(monkeypatch):
    monkeypatch.setenv("APPTUTORIAL_DENYLIST", "Foo.exe, Bar.EXE")

    cfg = load_config()

    assert cfg.denylist == ("foo.exe", "bar.exe")
