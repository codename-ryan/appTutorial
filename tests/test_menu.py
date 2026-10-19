from apptutorial.ui.menu import _default_options


def test_default_options_always_offers_choices():
    options = _default_options("Microsoft Excel")
    assert len(options) >= 2
    # every option is a (goal, kind) pair with real text
    assert all(goal and kind for goal, kind in options)
    # the app name is woven into the tailored defaults
    assert any("Microsoft Excel" in goal for goal, _ in options)


def test_default_options_handles_missing_app_name():
    options = _default_options(None)
    assert len(options) >= 2
    assert all(goal for goal, _ in options)
