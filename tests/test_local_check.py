from apptutorial.accessibility.local_check import cell_matches, evaluate_check
from apptutorial.ai.schemas import StepCheck, TutorialStep


def test_cell_matches_exact_and_anchor():
    assert cell_matches("B5", "B5")
    assert cell_matches("b5", "B5")  # case-insensitive
    assert cell_matches("B5:C10", "B5")  # anchor cell of a range
    assert not cell_matches("A1", "B5")
    assert not cell_matches("", "B5")
    assert not cell_matches("B5", "")


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
        check={"kind": "cell_selected", "expected": "B5"},
    )
    assert step.check.kind == "cell_selected"
    assert step.check.expected == "B5"
