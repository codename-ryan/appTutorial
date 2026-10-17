"""Anthropic client wrapper. Single choke point for all Claude calls + telemetry.

Implemented in M2. Routes every request so model/token/latency telemetry is recorded in
one place, and so screenshots/prompts are never persisted. See SPEC.md §8 and §11.
"""
