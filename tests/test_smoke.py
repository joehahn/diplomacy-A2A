"""End-to-end smoke test with a stub LLMClient — runs cheap, no API calls.

The stub returns canned responses so we can exercise the full game
loop (negotiation → orders → adjudication → transcript) without
spending tokens. Real-LLM end-to-end verification belongs in a
separate, opt-in test.
"""
from __future__ import annotations

import pytest


@pytest.mark.skip(reason="not yet implemented")
def test_one_turn_with_stub_llm() -> None:
    raise NotImplementedError
