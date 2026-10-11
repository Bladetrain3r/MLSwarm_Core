#!/usr/bin/env python3
"""Tests for the Claude provider's robustness, using a fake anthropic SDK so
they run without the real package or any network.

Run from agents/providers:

    python -m unittest discover -s tests
"""

import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import claude


# --- Fake SDK -------------------------------------------------------------
class FakeAPIStatusError(Exception):
    def __init__(self, message="", status_code=400):
        super().__init__(message)
        self.status_code = status_code


class FakeBadRequestError(FakeAPIStatusError):
    pass


class Block:
    def __init__(self, type, text=None):
        self.type = type
        self.text = text


class StopDetails:
    def __init__(self, category=None, explanation=None):
        self.category = category
        self.explanation = explanation


class Msg:
    def __init__(self, blocks, stop_reason="end_turn", stop_details=None):
        self.content = blocks
        self.stop_reason = stop_reason
        self.stop_details = stop_details


def install_fake_sdk(behaviors, record):
    """behaviors: list, one per create() call -- either a Msg to return or an
    Exception to raise. record: dict collecting the params of each call."""
    mod = types.SimpleNamespace()
    mod.APIStatusError = FakeAPIStatusError
    mod.BadRequestError = FakeBadRequestError

    class Messages:
        def create(self, **params):
            record["params"].append(params)
            outcome = behaviors[len(record["params"]) - 1]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    class Anthropic:
        def __init__(self, **kw):
            record["client_kwargs"] = kw
            self.messages = Messages()

    mod.Anthropic = Anthropic
    claude.anthropic = mod
    claude._HAVE_SDK = True
    return mod


class TestExtractText(unittest.TestCase):
    def test_skips_thinking_and_tool_blocks(self):
        msg = Msg([
            Block("thinking", None),
            Block("text", "hello "),
            Block("tool_use", None),
            {"type": "text", "text": "world"},   # dict-style block
        ])
        self.assertEqual(claude._extract_text(msg), "hello world")

    def test_empty_when_no_text_blocks(self):
        self.assertEqual(claude._extract_text(Msg([Block("thinking", None)])), "")


class TestGetClaudeResponse(unittest.TestCase):
    def setUp(self):
        self._saved = (claude.anthropic, claude._HAVE_SDK)

    def tearDown(self):
        claude.anthropic, claude._HAVE_SDK = self._saved

    def test_success_first_try(self):
        rec = {"params": []}
        install_fake_sdk([Msg([Block("text", "a jungle thought")])], rec)
        out = claude.get_claude_response("ctx", apikey="k")
        self.assertEqual(out, "a jungle thought")
        self.assertEqual(len(rec["params"]), 1)
        self.assertNotIn("temperature", rec["params"][0])  # removed API-wide

    def test_temperature_never_sent_even_when_passed(self):
        rec = {"params": []}
        install_fake_sdk([Msg([Block("text", "ok")])], rec)
        out = claude.get_claude_response("ctx", apikey="k", temperature=0.8)
        self.assertEqual(out, "ok")
        self.assertNotIn("temperature", rec["params"][0])

    def test_adapts_on_bad_request(self):
        rec = {"params": []}
        install_fake_sdk(
            [FakeBadRequestError("max_tokens: too large"), Msg([Block("text", "ok")])],
            rec)
        out = claude.get_claude_response("ctx", apikey="k")
        self.assertEqual(out, "ok")
        self.assertEqual(len(rec["params"]), 2)
        self.assertLess(rec["params"][1]["max_tokens"],
                        rec["params"][0]["max_tokens"])  # conservative rung

    def test_refusal_before_output_returns_none_without_retry(self):
        rec = {"params": []}
        install_fake_sdk(
            [Msg([], stop_reason="refusal",
                 stop_details=StopDetails("cyber", "nope"))],
            rec)
        out = claude.get_claude_response("ctx", apikey="k")
        self.assertIsNone(out)
        self.assertEqual(len(rec["params"]), 1)  # a refusal is not a param problem

    def test_midstream_refusal_drops_partial_text(self):
        rec = {"params": []}
        install_fake_sdk(
            [Msg([Block("text", "a stub cut off mid-")], stop_reason="refusal")],
            rec)
        out = claude.get_claude_response("ctx", apikey="k")
        self.assertIsNone(out)  # never post the truncated stub
        self.assertEqual(len(rec["params"]), 1)

    def test_status_error_returns_none_without_retry(self):
        rec = {"params": []}
        install_fake_sdk([FakeAPIStatusError("overloaded", 529)], rec)
        out = claude.get_claude_response("ctx", apikey="k")
        self.assertIsNone(out)
        self.assertEqual(len(rec["params"]), 1)  # not fixable by trimming params

    def test_no_sdk_returns_none(self):
        claude._HAVE_SDK = False
        self.assertIsNone(claude.get_claude_response("ctx", apikey="k"))

    def test_api_key_none_falls_back_to_env(self):
        rec = {"params": []}
        install_fake_sdk([Msg([Block("text", "hi")])], rec)
        claude.get_claude_response("ctx", apikey="None")  # sentinel -> env
        self.assertIsNone(rec["client_kwargs"]["api_key"])


if __name__ == "__main__":
    unittest.main()
