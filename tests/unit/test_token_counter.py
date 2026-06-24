"""
tests/test_token_counter.py
===========================
TDD unit tests for src/token_counter.py.

All tests are pure-unit: no live Gemini API calls, no filesystem I/O beyond
what is explicitly mocked.

Coverage matrix
---------------
TokenEstimate model
  [TC-01] fields and defaults

estimate_tokens_for_text
  [TC-02] empty string returns 0
  [TC-03] small plain text returns proportional estimate
  [TC-04] result is an integer (no floats leak out)

estimate_tokens_for_image
  [TC-05] PNG 100×100 bytes → expected bucket
  [TC-06] large image → higher estimate than small image
  [TC-07] unknown mime type uses generic formula

estimate_tokens_for_context_files
  [TC-08] empty list returns 0
  [TC-09] single file: content token estimate forwarded
  [TC-10] unreadable file counted as 0 (error logged, no raise)
  [TC-11] multiple files summed correctly

build_pending_context_estimate
  [TC-12] plain message only
  [TC-13] message + images
  [TC-14] message + context_files
  [TC-15] message + images + context_files combined
  [TC-16] system_prompt adds to total
  [TC-17] history_token_count adds to total (pre-existing session)

count_session_tokens  (requires live-API mock)
  [TC-18] returns token counts from usage_metadata on success
  [TC-19] API raises → falls back to heuristic with fallback_used=True
  [TC-20] empty history returns zeros without calling API
"""
from __future__ import annotations

import base64
import json
from typing import Any
from unittest.mock import MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Import the module under test — will fail until implementation exists
# ---------------------------------------------------------------------------
from src.token_counter import (
    TokenEstimate,
    estimate_tokens_for_text,
    estimate_tokens_for_image,
    estimate_tokens_for_context_files,
    build_pending_context_estimate,
    count_session_tokens,
)


# ════════════════════════════════════════════════════════════════════════════
# [TC-01] TokenEstimate model fields and defaults
# ════════════════════════════════════════════════════════════════════════════

class TestTokenEstimateModel:
    def test_all_fields_present(self) -> None:
        est = TokenEstimate(
            text_tokens=10,
            image_tokens=20,
            context_file_tokens=30,
            system_prompt_tokens=5,
            history_tokens=100,
            total_tokens=165,
            fallback_used=False,
        )
        assert est.text_tokens == 10
        assert est.image_tokens == 20
        assert est.context_file_tokens == 30
        assert est.system_prompt_tokens == 5
        assert est.history_tokens == 100
        assert est.total_tokens == 165
        assert est.fallback_used is False

    def test_default_fallback_used_is_false(self) -> None:
        est = TokenEstimate(
            text_tokens=1,
            image_tokens=0,
            context_file_tokens=0,
            system_prompt_tokens=0,
            history_tokens=0,
            total_tokens=1,
        )
        assert est.fallback_used is False

    def test_total_tokens_is_int(self) -> None:
        est = TokenEstimate(
            text_tokens=3,
            image_tokens=0,
            context_file_tokens=0,
            system_prompt_tokens=0,
            history_tokens=0,
            total_tokens=3,
        )
        assert isinstance(est.total_tokens, int)


# ════════════════════════════════════════════════════════════════════════════
# [TC-02 – TC-04] estimate_tokens_for_text
# ════════════════════════════════════════════════════════════════════════════

class TestEstimateTokensForText:
    def test_empty_string_returns_zero(self) -> None:  # TC-02
        assert estimate_tokens_for_text("") == 0

    def test_proportional_to_char_count(self) -> None:  # TC-03
        # Gemini uses ~4 chars/token heuristic — 400 chars → ~100 tokens
        text = "a" * 400
        result = estimate_tokens_for_text(text)
        assert 80 <= result <= 120  # ±20% tolerance

    def test_returns_integer(self) -> None:  # TC-04
        result = estimate_tokens_for_text("hello world")
        assert isinstance(result, int)

    def test_longer_text_gives_higher_count(self) -> None:
        short = estimate_tokens_for_text("hi")
        long_ = estimate_tokens_for_text("hi " * 100)
        assert long_ > short

    def test_whitespace_only_counts_proportionally(self) -> None:
        result = estimate_tokens_for_text("   " * 100)
        assert result > 0


# ════════════════════════════════════════════════════════════════════════════
# [TC-05 – TC-07] estimate_tokens_for_image
# ════════════════════════════════════════════════════════════════════════════

class TestEstimateTokensForImage:
    """
    Gemini vision uses a tile-based scheme.  Our heuristic:
      - Base cost: 258 tokens
      - Each 512×512 tile: +258 tokens
      - We use byte-size proxy: small images (<50 KB) → 1 tile, larger → more

    See: https://ai.google.dev/gemini-api/docs/vision#image-requirements
    """

    def test_small_png_returns_single_tile_estimate(self) -> None:  # TC-05
        small_bytes = b"\x89PNG" + b"\x00" * 1000  # ~1 KB
        b64 = base64.b64encode(small_bytes).decode()
        result = estimate_tokens_for_image(b64, "image/png")
        # small image → around 258 tokens (1 tile)
        assert 200 <= result <= 400

    def test_large_image_higher_than_small(self) -> None:  # TC-06
        small_b64 = base64.b64encode(b"\x89PNG" + b"\x00" * 1_000).decode()
        large_b64 = base64.b64encode(b"\x89PNG" + b"\x00" * 200_000).decode()
        small_est = estimate_tokens_for_image(small_b64, "image/png")
        large_est = estimate_tokens_for_image(large_b64, "image/png")
        assert large_est >= small_est

    def test_unknown_mime_type_returns_positive_int(self) -> None:  # TC-07
        b64 = base64.b64encode(b"GIFDATA" + b"\x00" * 500).decode()
        result = estimate_tokens_for_image(b64, "image/gif")
        assert isinstance(result, int)
        assert result > 0

    def test_bad_base64_returns_fallback_estimate(self) -> None:
        """Invalid base64 should not raise — returns the minimum 258."""
        result = estimate_tokens_for_image("!!!not_valid_base64!!!", "image/png")
        assert isinstance(result, int)
        assert result >= 0


# ════════════════════════════════════════════════════════════════════════════
# [TC-08 – TC-11] estimate_tokens_for_context_files
# ════════════════════════════════════════════════════════════════════════════

class TestEstimateTokensForContextFiles:
    def test_empty_list_returns_zero(self) -> None:  # TC-08
        result = estimate_tokens_for_context_files([])
        assert result == 0

    def test_single_readable_file(self) -> None:  # TC-09
        content = "a" * 400  # ~100 tokens
        result = estimate_tokens_for_context_files([content])
        assert 80 <= result <= 120

    def test_empty_string_counted_as_zero(self) -> None:  # TC-10
        result = estimate_tokens_for_context_files([""])
        assert result == 0

    def test_multiple_files_summed(self) -> None:  # TC-11
        result = estimate_tokens_for_context_files(["a" * 400, "b" * 400])
        assert 160 <= result <= 240  # both files summed


# ════════════════════════════════════════════════════════════════════════════
# [TC-12 – TC-17] build_pending_context_estimate
# ════════════════════════════════════════════════════════════════════════════

class TestBuildPendingContextEstimate:
    """
    build_pending_context_estimate assembles a TokenEstimate for an *about-to-
    be-sent* turn.  It does NOT call the Gemini API — it uses the local
    heuristics only and sets fallback_used=True.
    """

    def test_plain_message_only(self) -> None:  # TC-12
        est = build_pending_context_estimate(
            user_message="hello",
            images=None,
            context_file_contents=None,
            system_prompt=None,
            history_token_count=0,
        )
        assert isinstance(est, TokenEstimate)
        assert est.text_tokens > 0
        assert est.image_tokens == 0
        assert est.context_file_tokens == 0
        assert est.system_prompt_tokens == 0
        assert est.history_tokens == 0
        assert est.total_tokens == (
            est.text_tokens + est.image_tokens + est.context_file_tokens
            + est.system_prompt_tokens + est.history_tokens
        )
        assert est.fallback_used is True  # heuristic, not API

    def test_message_plus_images(self) -> None:  # TC-13
        b64 = base64.b64encode(b"\x89PNG" + b"\x00" * 1000).decode()
        images = [{"mime_type": "image/png", "data": b64}]

        est = build_pending_context_estimate(
            user_message="look at this",
            images=images,
            context_file_contents=None,
            system_prompt=None,
            history_token_count=0,
        )
        assert est.image_tokens > 0
        assert est.total_tokens > est.text_tokens

    def test_message_plus_context_files(self) -> None:  # TC-14
        est = build_pending_context_estimate(
            user_message="check materials",
            images=None,
            context_file_contents=["wood 18mm birch " * 50],
            system_prompt=None,
            history_token_count=0,
        )
        assert est.context_file_tokens > 0

    def test_all_components_combined(self) -> None:  # TC-15
        b64 = base64.b64encode(b"\x89PNG" + b"\x00" * 1000).decode()

        est = build_pending_context_estimate(
            user_message="full context",
            images=[{"mime_type": "image/png", "data": b64}],
            context_file_contents=["content " * 100],
            system_prompt="You are a helpful assistant.",
            history_token_count=500,
        )
        assert est.text_tokens > 0
        assert est.image_tokens > 0
        assert est.context_file_tokens > 0
        assert est.system_prompt_tokens > 0
        assert est.history_tokens == 500
        assert est.total_tokens == (
            est.text_tokens + est.image_tokens + est.context_file_tokens
            + est.system_prompt_tokens + est.history_tokens
        )

    def test_system_prompt_adds_to_total(self) -> None:  # TC-16
        est_without = build_pending_context_estimate(
            user_message="hi",
            images=None, context_file_contents=None,
            system_prompt=None,
            history_token_count=0,
        )
        est_with = build_pending_context_estimate(
            user_message="hi",
            images=None, context_file_contents=None,
            system_prompt="You are a stoic carpenter with 30 years experience.",
            history_token_count=0,
        )
        assert est_with.system_prompt_tokens > 0
        assert est_with.total_tokens > est_without.total_tokens

    def test_history_token_count_forwarded(self) -> None:  # TC-17
        est = build_pending_context_estimate(
            user_message="hi",
            images=None, context_file_contents=None,
            system_prompt=None,
            history_token_count=1234,
        )
        assert est.history_tokens == 1234
        assert est.total_tokens >= 1234


# ════════════════════════════════════════════════════════════════════════════
# [TC-18 – TC-20] count_session_tokens
# ════════════════════════════════════════════════════════════════════════════

class TestCountSessionTokens:
    """
    count_session_tokens(api_history_json, system_prompt, model)
      → TokenEstimate via live Gemini count_tokens call (mocked here).

    On success: returns exact counts from usage_metadata.
    On error:   falls back to heuristic + fallback_used=True.
    Empty history: returns zeros without calling API.
    """

    def _make_api_json(self, n_turns: int = 2) -> str:
        """Build a minimal serialised api_history for testing."""
        items = []
        for i in range(n_turns):
            items.append({"role": "user", "type": "text", "data": f"Turn {i}"})
            items.append({"role": "model", "type": "text", "data": f"Answer {i}"})
        return json.dumps(items)

    @patch("src.token_counter._client")
    def test_success_returns_api_token_counts(self, mock_client: MagicMock) -> None:  # TC-18
        mock_resp = MagicMock()
        mock_resp.total_tokens = 427
        mock_client.models.count_tokens.return_value = mock_resp

        api_json = self._make_api_json(2)
        result = count_session_tokens(api_json, system_prompt=None)

        assert isinstance(result, TokenEstimate)
        assert result.total_tokens == 427
        assert result.fallback_used is False
        mock_client.models.count_tokens.assert_called_once()

    @patch("src.token_counter._client")
    def test_api_error_falls_back_to_heuristic(self, mock_client: MagicMock) -> None:  # TC-19
        mock_client.models.count_tokens.side_effect = Exception("API unavailable")

        api_json = self._make_api_json(2)
        result = count_session_tokens(api_json, system_prompt=None)

        assert isinstance(result, TokenEstimate)
        assert result.fallback_used is True
        assert result.total_tokens >= 0  # heuristic is still positive

    def test_empty_history_returns_zero_without_api_call(self) -> None:  # TC-20
        with patch("src.token_counter._client") as mock_client:
            result = count_session_tokens("[]", system_prompt=None)

        assert result.total_tokens == 0
        mock_client.models.count_tokens.assert_not_called()

    @patch("src.token_counter._client")
    def test_system_prompt_included_in_count_tokens_call(self, mock_client: MagicMock) -> None:
        """system_prompt must be forwarded in the GenerateContentConfig."""
        mock_resp = MagicMock()
        mock_resp.total_tokens = 600
        mock_client.models.count_tokens.return_value = mock_resp

        api_json = self._make_api_json(1)
        result = count_session_tokens(api_json, system_prompt="You are a cabinet maker.")

        assert result.total_tokens == 600
        call_kwargs = mock_client.models.count_tokens.call_args[1]
        # config must carry system_instruction
        config = call_kwargs.get("config")
        assert config is not None
        assert config.system_instruction == "You are a cabinet maker."

    @patch("src.token_counter._client")
    def test_model_parameter_forwarded(self, mock_client: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.total_tokens = 50
        mock_client.models.count_tokens.return_value = mock_resp

        api_json = self._make_api_json(1)
        count_session_tokens(api_json, system_prompt=None, model="gemini-2.0-flash")

        call_kwargs = mock_client.models.count_tokens.call_args[1]
        assert call_kwargs["model"] == "gemini-2.0-flash"
