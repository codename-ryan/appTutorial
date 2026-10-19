"""AI client wrapper: the single choke point for all model calls.

Talks to an OpenAI-compatible endpoint, which is how open-weight vision models are almost
always served - locally via Ollama (default) or vLLM/llama.cpp, or a hosted open-weight
provider (OpenRouter, Together, Groq, ...). Routes every request through one place so
model/token/latency telemetry is recorded consistently and screenshots/prompts are never
persisted. With a local backend the screenshots never leave the machine at all. See SPEC.md
§8 and §11.
"""

from __future__ import annotations

import base64
import io
import time
from typing import Any, TypeVar

from PIL import Image
from pydantic import BaseModel, ValidationError

from apptutorial.telemetry.logger import TelemetryLogger

T = TypeVar("T", bound=BaseModel)

# Downscale screenshots before sending them to the model. A full-resolution window shot gives a
# local vision model far too much to process (very slow, and it can blow past the request
# timeout); ~1280px keeps UI text legible while cutting inference time dramatically. Models
# downscale internally anyway, so accuracy barely changes.
_MAX_IMAGE_EDGE = 1280


def _downscale_png(png_bytes: bytes) -> bytes:
    try:
        image = Image.open(io.BytesIO(png_bytes))
        if max(image.size) <= _MAX_IMAGE_EDGE:
            return png_bytes
        image = image.convert("RGB")
        image.thumbnail((_MAX_IMAGE_EDGE, _MAX_IMAGE_EDGE))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
    except Exception:
        return png_bytes  # send the original if anything goes wrong


class AIError(RuntimeError):
    """Any failure talking to the model (no backend, network/API error, or bad output)."""


def image_content_block(png_bytes: bytes) -> dict[str, Any]:
    """An OpenAI-style image content block carrying a (downscaled) PNG as an inline data URI."""
    b64 = base64.standard_b64encode(_downscale_png(png_bytes)).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}


class AIClient:
    """Thin wrapper over the OpenAI SDK (pointed at an open-weight backend) with structured
    output + telemetry."""

    def __init__(
        self, base_url: str | None, api_key: str | None, telemetry: TelemetryLogger
    ) -> None:
        self._telemetry = telemetry
        self._base_url = base_url
        self._client = None
        if not base_url:
            return
        try:
            from openai import OpenAI
        except Exception:
            return
        # Local inference can be slow (first call also loads the model into memory), so allow a
        # generous timeout. The api_key is unused by local backends (Ollama); a placeholder keeps
        # the SDK happy.
        self._client = OpenAI(base_url=base_url, api_key=api_key or "not-needed", timeout=300.0)

    @property
    def available(self) -> bool:
        """True if a backend URL is configured and the SDK is importable."""
        return self._client is not None

    def parse(
        self,
        *,
        model: str,
        call_type: str,
        messages: list[dict[str, Any]],
        output_model: type[T],
        max_tokens: int = 1024,
        system: str | None = None,
        step_index: int | None = None,
    ) -> T:
        """Call the chat endpoint with a JSON-schema response format and return the validated
        structured output. Raises AIError on any failure. Always records a telemetry event."""
        if self._client is None:
            raise AIError(
                "No AI backend configured. Set OPENWEIGHT_BASE_URL in .env "
                "(default is a local Ollama server at http://localhost:11434/v1)."
            )

        full_messages: list[dict[str, Any]] = []
        if system is not None:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": output_model.__name__,
                "schema": output_model.model_json_schema(),
            },
        }

        start = time.monotonic()
        status = "ok"
        input_tokens = output_tokens = 0
        try:
            completion = self._client.chat.completions.create(
                model=model,
                messages=full_messages,
                max_tokens=max_tokens,
                temperature=0,
                response_format=response_format,
            )
            usage = getattr(completion, "usage", None)
            if usage is not None:
                input_tokens = getattr(usage, "prompt_tokens", 0) or 0
                output_tokens = getattr(usage, "completion_tokens", 0) or 0
            content = completion.choices[0].message.content or ""
            result = _validate(content, output_model)
        except AIError:
            status = "error"
            raise
        except Exception as exc:  # network / API / validation
            status = "error"
            raise AIError(f"{type(exc).__name__}: {exc}") from exc
        else:
            return result
        finally:
            self._telemetry.log(
                model=model,
                call_type=call_type,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=int((time.monotonic() - start) * 1000),
                step_index=step_index,
                status=status,
            )


def _validate(content: str, output_model: type[T]) -> T:
    """Validate the model's text as the Pydantic model, tolerating stray prose/code fences."""
    try:
        return output_model.model_validate_json(content)
    except ValidationError:
        pass
    start, end = content.find("{"), content.rfind("}")
    if start != -1 and end > start:
        try:
            return output_model.model_validate_json(content[start : end + 1])
        except ValidationError as exc:
            raise AIError(f"model returned JSON that didn't match the schema: {exc}") from exc
    raise AIError("model did not return JSON output")
