from apptutorial.ai.schemas import TutorialStep
from apptutorial.app import _cell_ref_of_step, _looks_like_cell


def _step(instruction="Do a thing.", name_hint=None, check=None):
    return TutorialStep(
        index=0,
        instruction=instruction,
        rationale="r",
        target={"description": "x", "uia_name_hint": name_hint},
        done_when="something",
        check=check or {"kind": "visual"},
    )


def test_looks_like_cell():
    assert _looks_like_cell("B5")
    assert _looks_like_cell("A1:C10")
    assert _looks_like_cell("$B$5")
    assert not _looks_like_cell("Developer")
    assert not _looks_like_cell("")
    assert not _looks_like_cell(None)


def test_cell_ref_from_cell_value_target():
    step = _step(check={"kind": "cell_value", "target": "A11", "expected": "42"})
    assert _cell_ref_of_step(step) == "A11"


def test_cell_ref_from_cell_selected_in_expected():
    # planner put the ref in `expected` instead of `target` — still found.
    step = _step(check={"kind": "cell_selected", "expected": "B5"})
    assert _cell_ref_of_step(step) == "B5"


def test_cell_ref_from_name_hint_when_check_is_mislabeled():
    step = _step(name_hint="C7", check={"kind": "visual"})
    assert _cell_ref_of_step(step) == "C7"


def test_cell_ref_from_instruction_mention():
    step = _step(instruction="Select cell D9 to begin.", check={"kind": "visual"})
    assert _cell_ref_of_step(step) == "D9"


def test_cell_ref_none_for_non_cell_step():
    step = _step(
        instruction="Click the Developer tab.",
        name_hint="Developer",
        check={"kind": "element_selected", "target": "Developer"},
    )
    assert _cell_ref_of_step(step) is None
