from apptutorial.accessibility.local_check import cell_matches, evaluate_check, value_matches
from apptutorial.ai.schemas import StepCheck, TutorialStep


def test_cell_matches_exact_and_anchor():
    assert cell_matches("B5", "B5")
    assert cell_matches("b5", "B5")  # case-insensitive
    assert cell_matches("B5:C10", "B5")  # anchor cell of a range
    assert not cell_matches("A1", "B5")
    assert not cell_matches("", "B5")
    assert not cell_matches("B5", "")


def test_value_matches_numbers_formulas_and_blank():
    assert value_matches("42", "42", "42")  # exact
    assert value_matches("42.0", "42", "42")  # numeric equivalence
    assert value_matches("55", "=SUM(A1:A10)", "=SUM(A1:A10)")  # formula match
    assert value_matches("55", "=SUM(A1:A10)", "SUM(A1:A10)")  # formula without '='
    assert value_matches("42", "42", "")  # blank expected => any non-empty value
    assert not value_matches("", "", "")  # blank cell, blank expected
    assert not value_matches("abc", "abc", "42")


def test_evaluate_check_visual_is_none_without_uia():
    # "visual" short-circuits before importing uiautomation, so this is safe on any platform.
    assert evaluate_check(0, "visual", None, None) is None
    assert evaluate_check(0, "", None, None) is None
    assert evaluate_check(0, None, None, None) is None


def test_step_check_defaults_to_visual():
    check = StepCheck()
    assert check.kind == "visual"
    assert check.target is None
    assert check.expected is None


def test_tutorial_step_has_default_visual_check():
    step = TutorialStep(
        index=0,
        instruction="Click the Developer tab.",
        rationale="r",
        target={"description": "Developer tab"},
        done_when="The Developer ribbon is shown.",
    )
    assert step.check.kind == "visual"


def test_tutorial_step_parses_cell_selected_check():
    step = TutorialStep(
        index=1,
        instruction="Select cell B5.",
        rationale="r",
        target={"description": "cell B5"},
        done_when="Cell B5 is selected.",
        check={"kind": "cell_selected", "target": "B5"},
    )
    assert step.check.kind == "cell_selected"
    assert step.check.target == "B5"


def test_tutorial_step_parses_cell_value_check():
    step = TutorialStep(
        index=2,
        instruction="Type 42 in cell A11 and press Enter.",
        rationale="r",
        target={"description": "cell A11"},
        done_when="Cell A11 shows 42.",
        check={"kind": "cell_value", "target": "A11", "expected": "42"},
    )
    assert step.check.kind == "cell_value"
    assert step.check.target == "A11"
    assert step.check.expected == "42"
