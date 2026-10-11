#!/usr/bin/env python3
"""Robustness tests for the grok / gpt / gemini / ollama providers.

Each provider's network/SDK boundary is faked, so these run offline. Focus:
robust text extraction and the parameter-adaptation ladders.

Run from agents/providers:

    python -m unittest discover -s tests
"""

import json
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import grok
import gpt
import gemini
import ollama


class FakeHTTP:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


# --------------------------------------------------------------------------
# grok (requests, OpenAI-compatible)
# --------------------------------------------------------------------------
class TestGrok(unittest.TestCase):
    def setUp(self):
        self._post = grok.requests.post

    def tearDown(self):
        grok.requests.post = self._post

    def test_extract_plain_and_reasoning(self):
        self.assertEqual(
            grok._extract_text({"choices": [{"message": {"content": "hi there."}}]}),
            "hi there.")
        self.assertEqual(
            grok._extract_text({"choices": [{"message": {"content": None,
                               "reasoning_content": "from reasoning."}}]}),
            "from reasoning.")
        self.assertIsNone(grok._extract_text({"choices": []}))

    def test_temperature_ladder_on_400(self):
        seen = []

        def fake_post(url, headers=None, data=None, timeout=None):
            payload = json.loads(data)
            seen.append(payload)
            if "temperature" in payload:            # first attempt -> reject
                return FakeHTTP(400, text="temperature not supported")
            return FakeHTTP(200, {"choices": [{"message": {"content": "done."}}]})

        grok.requests.post = fake_post
        out = grok.get_grok_response("ctx", apikey="k")
        self.assertEqual(out, "done.")
        self.assertEqual(len(seen), 2)
        self.assertIn("temperature", seen[0])
        self.assertNotIn("temperature", seen[1])   # ladder dropped it

    def test_non_400_error_returns_none(self):
        grok.requests.post = lambda *a, **k: FakeHTTP(401, text="bad key")
        self.assertIsNone(grok.get_grok_response("ctx", apikey="k"))


# --------------------------------------------------------------------------
# gpt (openai Responses API)
# --------------------------------------------------------------------------
class _BadRequest(Exception):
    pass


class _APIStatus(Exception):
    pass


class FakeResponses:
    def __init__(self, behaviors, seen):
        self._behaviors = behaviors
        self._seen = seen

    def create(self, **params):
        self._seen.append(params)
        outcome = self._behaviors[len(self._seen) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def fake_openai_response(output_text="", output=None):
    return types.SimpleNamespace(output_text=output_text, output=output or [])


class TestGpt(unittest.TestCase):
    def setUp(self):
        self._saved = (gpt.OpenAI, gpt.openai_mod, gpt._HAVE_SDK)
        gpt.openai_mod = types.SimpleNamespace(BadRequestError=_BadRequest,
                                               APIStatusError=_APIStatus)
        gpt._HAVE_SDK = True

    def tearDown(self):
        gpt.OpenAI, gpt.openai_mod, gpt._HAVE_SDK = self._saved

    def _install(self, behaviors, seen):
        class FakeClient:
            def __init__(self):
                self.responses = FakeResponses(behaviors, seen)
        gpt.OpenAI = FakeClient

    def test_reasoning_ladder_on_400(self):
        seen = []
        self._install([_BadRequest("reasoning unsupported"),
                       fake_openai_response("plain answer")], seen)
        out = gpt.get_gpt_response("ctx")
        self.assertEqual(out, "plain answer")
        self.assertEqual(len(seen), 2)
        self.assertIn("reasoning", seen[0])
        self.assertNotIn("reasoning", seen[1])     # ladder dropped it

    def test_extract_fallback_to_output_parts(self):
        item = types.SimpleNamespace(content=[types.SimpleNamespace(text="from parts")])
        self.assertEqual(gpt._extract_output_text(fake_openai_response("", [item])),
                         "from parts")

    def test_status_error_returns_none(self):
        seen = []
        self._install([_APIStatus("overloaded")], seen)
        self.assertIsNone(gpt.get_gpt_response("ctx"))
        self.assertEqual(len(seen), 1)

    def test_no_sdk_returns_none(self):
        gpt._HAVE_SDK = False
        self.assertIsNone(gpt.get_gpt_response("ctx"))


# --------------------------------------------------------------------------
# gemini (google-genai)
# --------------------------------------------------------------------------
class TestGemini(unittest.TestCase):
    def test_extract_handles_raising_text(self):
        class Boom:
            @property
            def text(self):
                raise ValueError("no valid Part")
            candidates = [types.SimpleNamespace(
                content=types.SimpleNamespace(
                    parts=[types.SimpleNamespace(text="recovered")]))]
        self.assertEqual(gemini._extract_text(Boom()), "recovered")

    def test_extract_blocked_returns_none(self):
        class Blocked:
            @property
            def text(self):
                raise ValueError("blocked")
            candidates = []
        self.assertIsNone(gemini._extract_text(Blocked()))

    def test_extract_plain_text(self):
        self.assertEqual(
            gemini._extract_text(types.SimpleNamespace(text="  hello  ")), "hello")

    def test_no_sdk_returns_none(self):
        saved = gemini._HAVE_SDK
        gemini._HAVE_SDK = False
        try:
            self.assertIsNone(gemini.get_gemini_response("ctx", apikey="k"))
        finally:
            gemini._HAVE_SDK = saved


# --------------------------------------------------------------------------
# ollama (local requests)
# --------------------------------------------------------------------------
class TestOllama(unittest.TestCase):
    def setUp(self):
        self._post = ollama.requests.post

    def tearDown(self):
        ollama.requests.post = self._post

    def test_extract_content_then_reasoning(self):
        self.assertEqual(
            ollama._extract_text({"choices": [{"message": {"content": "hi"}}]}), "hi")
        self.assertEqual(
            ollama._extract_text({"choices": [{"message": {"content": "  ",
                                "reasoning": "thought"}}]}), "thought")
        self.assertIsNone(ollama._extract_text({}))

    def test_success(self):
        ollama.requests.post = lambda *a, **k: FakeHTTP(
            200, {"choices": [{"message": {"content": "local out"}}]})
        self.assertEqual(ollama.get_local_response("ctx"), "local out")

    def test_connection_error_returns_none(self):
        def boom(*a, **k):
            raise ollama.requests.exceptions.ConnectionError("refused")
        ollama.requests.post = boom
        self.assertIsNone(ollama.get_local_response("ctx"))


if __name__ == "__main__":
    unittest.main()
