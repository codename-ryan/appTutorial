"""Local JSONL telemetry: one event per API call.

Records only metadata (model, tokens, latency, step, status). Never records screenshots
or prompt/response bodies. See SPEC.md §11.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path


class TelemetryLogger:
    """Appends one JSON line per API call."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def log(
        self,
        *,
        model: str,
        call_type: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
        status: str,
        step_index: int | None = None,
    ) -> None:
        event = {
            "ts": datetime.now(UTC).isoformat(),
            "call_type": call_type,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": latency_ms,
            "step_index": step_index,
            "status": status,
        }
        try:
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event) + "\n")
        except OSError:
            # Telemetry must never break the app.
            pass
