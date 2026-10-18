import json

from apptutorial.telemetry.logger import TelemetryLogger


def test_log_writes_jsonl_without_screen_content(tmp_path):
    path = tmp_path / "telemetry.jsonl"
    logger = TelemetryLogger(path)

    logger.log(
        model="claude-sonnet-5",
        call_type="identify",
        input_tokens=120,
        output_tokens=45,
        latency_ms=1337,
        status="ok",
    )

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["model"] == "claude-sonnet-5"
    assert event["call_type"] == "identify"
    assert event["input_tokens"] == 120
    assert event["output_tokens"] == 45
    assert event["latency_ms"] == 1337
    assert event["status"] == "ok"
    assert event["step_index"] is None

    # Privacy invariant: telemetry never contains screen content or prompt bodies.
    for forbidden in ("screenshot", "png", "png_bytes", "image", "prompt", "messages"):
        assert forbidden not in event


def test_log_appends(tmp_path):
    path = tmp_path / "telemetry.jsonl"
    logger = TelemetryLogger(path)
    logger.log(
        model="m",
        call_type="identify",
        input_tokens=1,
        output_tokens=1,
        latency_ms=1,
        status="ok",
    )
    logger.log(
        model="m",
        call_type="verify",
        input_tokens=1,
        output_tokens=1,
        latency_ms=1,
        status="error",
        step_index=2,
    )
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["step_index"] == 2
