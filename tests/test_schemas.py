from apptutorial.ai.schemas import AppIdentification, TutorialPlan


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


def test_tutorial_plan_parses_nested_steps():
    plan = TutorialPlan(
        goal="Record a macro",
        app_name="Microsoft Excel",
        steps=[
            {
                "index": 0,
                "instruction": "Open the Developer tab.",
                "rationale": "The macro tools live on the Developer tab.",
                "target": {
                    "description": "Developer tab in the ribbon",
                    "uia_name_hint": "Developer",
                    "uia_role_hint": "TabItem",
                },
                "done_when": "The Developer ribbon is shown.",
                "done_signals": ["Record Macro button is visible"],
            }
        ],
    )
    assert plan.steps[0].index == 0
    assert plan.steps[0].target.uia_name_hint == "Developer"
    assert plan.steps[0].done_signals == ["Record Macro button is visible"]


def test_tutorial_plan_defaults_to_no_steps():
    plan = TutorialPlan(goal="x", app_name="y")
    assert plan.steps == []
