"""Anthropic client wrapper: the single choke point for all Claude calls.

Routes every request through one place so model/token/latency telemetry is recorded
consistently and screenshots/prompts are never persisted. See SPEC.md §8 and §11.
"""

from __future__ import annotations

import time
from typing import Any, TypeVar

import anthropic
from pydantic import BaseModel

from apptutorial.telemetry.logger import TelemetryLogger

T = TypeVar("T", bound=BaseModel)


class AIError(RuntimeError):
    """Any failure talking to Claude (no key, network/API error, refusal, bad output)."""


class AIClient:
    """Thin wrapper over the Anthropic SDK with structured output + telemetry."""

    def __init__(self, api_key: str | None, telemetry: TelemetryLogger) -> None:
        self._client = anthropic.Anthropic(api_key=api_key) if api_key else None
        self._telemetry = telemetry

    @property
    def available(self) -> bool:
        """True if an API key is configured and a client was created."""
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
        thinking: dict[str, Any] | None = None,
        step_index: int | None = None,
    ) -> T:
        """Call messages.parse and return the validated structured output.

        Raises AIError on any failure. Always records a telemetry event.
        """
        if self._client is None:
            raise AIError("No ANTHROPIC_API_KEY configured. Add it to .env to enable AI features.")

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
            "output_format": output_model,
        }
        if system is not None:
            kwargs["system"] = system
        if thinking is not None:
            kwargs["thinking"] = thinking

        start = time.monotonic()
        status = "ok"
        response = None
        try:
            response = self._client.messages.parse(**kwargs)
            if response.stop_reason == "refusal":
                status = "refusal"
                raise AIError("The model declined this request.")
            result = _extract_parsed(response, output_model)
        except AIError:
            if status != "refusal":
                status = "error"
            raise
        except Exception as exc:  # network / API / validation
            status = "error"
            raise AIError(str(exc)) from exc
        else:
            return result
        finally:
            input_tokens = output_tokens = 0
            usage = getattr(response, "usage", None)
            if usage is not None:
                input_tokens = usage.input_tokens or 0
                output_tokens = usage.output_tokens or 0
            self._telemetry.log(
                model=model,
                call_type=call_type,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=int((time.monotonic() - start) * 1000),
                step_index=step_index,
                status=status,
            )


def _extract_parsed(response: Any, output_model: type[T]) -> T:
    """Pull the validated model off the response's text block (SDK 1.x shape)."""
    for block in response.content:
        if getattr(block, "type", None) == "text":
            parsed = getattr(block, "parsed_output", None)
            if isinstance(parsed, output_model):
                return parsed
    raise AIError("Model response did not contain the expected structured output.")
