"""Local JSONL telemetry: one event per API call.

Event shape: {ts, model, call_type, input_tokens, output_tokens, latency_ms, step_index,
status}. Never records screenshots or prompt/response bodies. Implemented in M2.
See SPEC.md §11.
"""
