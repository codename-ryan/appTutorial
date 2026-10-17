from apptutorial.ai.schemas import AppIdentification


def test_app_identification_parses_nested_tutorials():
    ident = AppIdentification(
        app_name="Microsoft Excel",
        app_category="spreadsheet",
        confidence=0.9,
        current_context="A blank workbook with the Home tab active.",
        visible_capabilities=["ribbon", "formula bar"],
        suggested_tutorials=[{"id": "basic-tour", "title": "Tour of Excel", "kind": "tour"}],
    )
    assert ident.app_name == "Microsoft Excel"
    assert ident.detected_version_hint is None
    assert ident.suggested_tutorials[0].kind == "tour"


def test_app_identification_defaults():
    ident = AppIdentification(
        app_name="X",
        app_category="y",
        confidence=0.1,
        current_context="z",
    )
    assert ident.visible_capabilities == []
    assert ident.suggested_tutorials == []
