from apptutorial.ai.schemas import StepVerification, Target, TutorialStep
from apptutorial.ai.verify import verify_step
from apptutorial.config import VERIFY_MODEL


class _FakeClient:
    """Stand-in for AIClient that records the parse() call and returns a canned result."""

    def __init__(self, result):
        self._result = result
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return self._result


def _step():
    return TutorialStep(
        index=1,
        instruction="Click the Developer tab.",
        rationale="The macro tools live on the Developer tab.",
        target=Target(description="Developer tab in the ribbon"),
        done_when="The Developer ribbon is shown.",
        done_signals=["Record Macro button is visible"],
    )


def test_verify_step_routes_to_haiku_with_step_index():
    result = StepVerification(status="done", confidence=0.9, observation="Ribbon is shown.")
    client = _FakeClient(result)

    out = verify_step(client, b"fake-png-bytes", _step(), "Microsoft Excel")

    assert out is result
    call = client.calls[0]
    assert call["model"] == VERIFY_MODEL
    assert call["call_type"] == "verify"
    assert call["step_index"] == 1
    assert call["output_model"] is StepVerification


def test_verify_step_sends_screenshot_as_image_block():
    client = _FakeClient(
        StepVerification(status="not_done", confidence=0.3, observation="No change.")
    )
    verify_step(client, b"fake-png-bytes", _step(), "Microsoft Excel")

    content = client.calls[0]["messages"][0]["content"]
    assert content[0]["type"] == "image"
    assert content[0]["source"]["media_type"] == "image/png"
    assert content[1]["type"] == "text"


def test_verify_step_includes_uia_elements_when_provided():
    client = _FakeClient(
        StepVerification(status="done", confidence=0.8, observation="Tab is selected.")
    )
    verify_step(
        client,
        b"fake-png-bytes",
        _step(),
        "Microsoft Excel",
        elements_text="TabItem: Developer (selected)",
    )
    text = client.calls[0]["messages"][0]["content"][1]["text"]
    assert "Developer (selected)" in text
    assert "accessibility tree" in text


def test_step_verification_hint_defaults_to_none():
    verification = StepVerification(
        status="not_done", confidence=0.4, observation="Nothing changed."
    )
    assert verification.hint is None
