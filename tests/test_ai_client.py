import pytest

from apptutorial.ai.client import AIClient, AIError
from apptutorial.ai.schemas import AppIdentification
from apptutorial.telemetry.logger import TelemetryLogger


def test_unavailable_without_api_key(tmp_path):
    client = AIClient(None, TelemetryLogger(tmp_path / "t.jsonl"))
    assert client.available is False


def test_parse_without_key_raises(tmp_path):
    client = AIClient(None, TelemetryLogger(tmp_path / "t.jsonl"))
    with pytest.raises(AIError):
        client.parse(
            model="claude-sonnet-5",
            call_type="identify",
            messages=[],
            output_model=AppIdentification,
        )
