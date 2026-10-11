#!/usr/bin/env python3
"""Tests for the legacy Claude shim, using a fake requests module so they run
without the real package or any network.

Run from agents/lib/providers (or agents/providers):

    python -m unittest discover -s tests
"""

import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import claude_legacy


class FakeResponse:
    def __init__(self, status_code=200, body=None, text=""):
        self.status_code = status_code
        self._body = body or {}
        self.text = text

    def json(self):
        return self._body


def install_fake_requests(response, record):
    """record: dict collecting the kwargs of each post()."""
    mod = types.SimpleNamespace()

    def post(url, **kwargs):
        record["calls"].append({"url": url, **kwargs})
        if isinstance(response, Exception):
            raise response
        return response

    mod.post = post
    claude_legacy.requests = mod
    claude_legacy._HAVE_REQUESTS = True


def ok_body(text="hello", stop_reason="end_turn", **extra):
    return {"content": [{"type": "text", "text": text}],
            "stop_reason": stop_reason, **extra}


class TestNormalizeModel(unittest.TestCase):
    def test_retired_rewritten(self):
        self.assertEqual(claude_legacy._normalize_model("claude-3-opus-20240229"),
                         "claude-opus-4-5")
        self.assertEqual(claude_legacy._normalize_model("claude-3-5-haiku-20241022"),
                         "claude-haiku-4-5")

    def test_deprecated_passes_through(self):
        self.assertEqual(claude_legacy._normalize_model("claude-opus-4-1"),
                         "claude-opus-4-1")

    def test_unknown_passes_through(self):
        self.assertEqual(claude_legacy._normalize_model("claude-haiku-5-5"),
                         "claude-haiku-5-5")

    def test_keep_models_env_exempts_retired_id(self):
        os.environ["CLAUDE_LEGACY_KEEP_MODELS"] = "claude-3-opus-20240229"
        try:
            self.assertEqual(
                claude_legacy._normalize_model("claude-3-opus-20240229"),
                "claude-3-opus-20240229")  # granted-access door
        finally:
            del os.environ["CLAUDE_LEGACY_KEEP_MODELS"]


class TestSamplingGate(unittest.TestCase):
    def test_45_generation_allows(self):
        for m in ("claude-haiku-4-5", "claude-sonnet-4-5", "claude-opus-4-5",
                  "claude-3-haiku-20240307"):
            self.assertTrue(claude_legacy._sampling_allowed(m), m)

    def test_46_plus_denies(self):
        for m in ("claude-haiku-5-5", "claude-sonnet-4-6", "claude-opus-4-6",
                  "claude-opus-5-5", "claude-sonnet-5"):
            self.assertFalse(claude_legacy._sampling_allowed(m), m)


class TestGetClaudeResponse(unittest.TestCase):
    def setUp(self):
        self._saved = (claude_legacy.requests, claude_legacy._HAVE_REQUESTS)
        self.rec = {"calls": []}

    def tearDown(self):
        claude_legacy.requests, claude_legacy._HAVE_REQUESTS = self._saved

    def sent(self, i=0):
        return self.rec["calls"][i]["json"]

    def test_temperature_sent_to_old_generation(self):
        install_fake_requests(FakeResponse(body=ok_body()), self.rec)
        out = claude_legacy.get_claude_response(
            "ctx", claudemodel="claude-haiku-4-5", apikey="k")
        self.assertEqual(out, "hello")
        self.assertEqual(self.sent()["temperature"], 0.7)

    def test_temperature_stripped_for_current_generation(self):
        install_fake_requests(FakeResponse(body=ok_body()), self.rec)
        out = claude_legacy.get_claude_response(
            "ctx", claudemodel="claude-haiku-5-5", apikey="k", temperature=0.9)
        self.assertEqual(out, "hello")
        self.assertNotIn("temperature", self.sent())

    def test_retired_model_rewritten_in_payload(self):
        install_fake_requests(FakeResponse(body=ok_body()), self.rec)
        claude_legacy.get_claude_response(
            "ctx", claudemodel="claude-3-opus-20240229", apikey="k")
        self.assertEqual(self.sent()["model"], "claude-opus-4-5")
        self.assertIn("temperature", self.sent())  # target still takes it

    def test_refusal_drops_partial_text(self):
        install_fake_requests(
            FakeResponse(body=ok_body("a stub cut off mid-", stop_reason="refusal",
                                      stop_details={"category": "cyber"})),
            self.rec)
        out = claude_legacy.get_claude_response("ctx", apikey="k")
        self.assertIsNone(out)

    def test_thinking_first_content_extracts_text(self):
        body = {"content": [{"type": "thinking", "thinking": ""},
                            {"type": "text", "text": "the actual post"}],
                "stop_reason": "end_turn"}
        install_fake_requests(FakeResponse(body=body), self.rec)
        out = claude_legacy.get_claude_response("ctx", apikey="k")
        self.assertEqual(out, "the actual post")

    def test_http_error_returns_none(self):
        install_fake_requests(FakeResponse(status_code=400, text="bad"), self.rec)
        self.assertIsNone(claude_legacy.get_claude_response("ctx", apikey="k"))

    def test_network_error_returns_none(self):
        install_fake_requests(ConnectionError("down"), self.rec)
        self.assertIsNone(claude_legacy.get_claude_response("ctx", apikey="k"))

    def test_no_requests_lib_returns_none(self):
        claude_legacy._HAVE_REQUESTS = False
        self.assertIsNone(claude_legacy.get_claude_response("ctx", apikey="k"))

    def test_no_key_returns_none_without_call(self):
        install_fake_requests(FakeResponse(body=ok_body()), self.rec)
        env = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            out = claude_legacy.get_claude_response("ctx", apikey="None")
        finally:
            if env is not None:
                os.environ["ANTHROPIC_API_KEY"] = env
        self.assertIsNone(out)
        self.assertEqual(len(self.rec["calls"]), 0)


if __name__ == "__main__":
    unittest.main()
