import pytest

from apptutorial.ai.client import AIClient, AIError, image_content_block
from apptutorial.ai.schemas import AppIdentification
from apptutorial.telemetry.logger import TelemetryLogger


def test_unavailable_without_backend(tmp_path):
    client = AIClient(None, None, TelemetryLogger(tmp_path / "t.jsonl"))
    assert client.available is False


def test_parse_without_backend_raises(tmp_path):
    client = AIClient(None, None, TelemetryLogger(tmp_path / "t.jsonl"))
    with pytest.raises(AIError):
        client.parse(
            model="qwen2.5vl",
            call_type="identify",
            messages=[],
            output_model=AppIdentification,
        )


def test_image_content_block_is_openai_data_uri():
    block = image_content_block(b"\x89PNG-bytes")
    assert block["type"] == "image_url"
    assert block["image_url"]["url"].startswith("data:image/png;base64,")
