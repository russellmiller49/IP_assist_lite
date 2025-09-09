#!/usr/bin/env python3
"""
Unit tests for GPT‑5 model family handling in GPT5Medical wrapper.
"""
import os
import unittest
from unittest.mock import Mock, patch
from pathlib import Path
import sys

# Make src importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from llm.gpt5_medical import GPT5Medical


class TestGpt5ModelFamily(unittest.TestCase):
    def test_coerce_unknown_gpt5_variant(self):
        m = GPT5Medical(model="gpt-5-turbo", use_responses=False)
        self.assertEqual(m.model, "gpt-5")

    def test_allowed_family_pass_through(self):
        for name in ["gpt-5", "gpt-5-mini", "gpt-5-nano"]:
            m = GPT5Medical(model=name, use_responses=False)
            self.assertEqual(m.model, name)

    @patch.dict(os.environ, {"IP_GPT5_MODEL": "gpt-5-mini"}, clear=False)
    def test_env_precedence_ip_model(self):
        m = GPT5Medical(model=None, use_responses=False)
        self.assertEqual(m.model, "gpt-5-mini")

    @patch.dict(os.environ, {"GPT5_MODEL": "gpt-5-nano"}, clear=False)
    def test_env_fallback_gpt5_model(self):
        # Clear IP_GPT5_MODEL for this test
        os.environ.pop("IP_GPT5_MODEL", None)
        m = GPT5Medical(model=None, use_responses=False)
        self.assertEqual(m.model, "gpt-5-nano")

    def test_chat_uses_max_tokens(self):
        m = GPT5Medical(model="gpt-5-mini", use_responses=False, max_out=777)
        with patch.object(m.client.chat.completions, "create") as mock_create:
            # Minimal valid mock response
            mock_msg = Mock(); mock_msg.content = "ok"; mock_msg.tool_calls = None
            mock_choice = Mock(); mock_choice.message = mock_msg
            mock_resp = Mock(); mock_resp.choices = [mock_choice]
            mock_create.return_value = mock_resp

            _ = m.complete([{"role": "user", "content": "hi"}])
            kwargs = mock_create.call_args.kwargs
            assert "max_tokens" in kwargs, "max_tokens must be used for Chat Completions"
            assert kwargs["max_tokens"] == 777
            assert "max_completion_tokens" not in kwargs


if __name__ == "__main__":
    unittest.main()

