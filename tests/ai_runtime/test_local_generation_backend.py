"""Tests for local generation backend routing."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ai_runtime.services.local_generation import (
    LocalGenerationService,
    get_local_generation_service,
    reset_local_generation_services_for_tests,
)
from ai_runtime.services.local_generation_base import effective_max_input_tokens
from ai_runtime.services.local_generation_llama_cpp import LlamaCppLocalGenerationService


@pytest.fixture(autouse=True)
def _reset_state() -> None:
    reset_local_generation_services_for_tests()
    yield
    reset_local_generation_services_for_tests()


class TestLocalGenerationBackendRouting:
    @pytest.mark.asyncio
    async def test_llama_cpp_backend_selected(self) -> None:
        with patch.object(
            LlamaCppLocalGenerationService,
            "generate",
            new_callable=AsyncMock,
            return_value=('{"ok": true}', 3, 5),
        ) as generate:
            raw, inp, out = await LocalGenerationService().generate(
                system_prompt="sys",
                human_message="user",
                max_tokens=64,
                temperature=0.0,
            )
        generate.assert_awaited_once()
        assert raw == '{"ok": true}'
        assert inp == 3
        assert out == 5

    def test_get_local_generation_service_singleton(self) -> None:
        first = get_local_generation_service()
        second = get_local_generation_service()
        assert first is second

    @pytest.mark.asyncio
    async def test_llama_cpp_create_chat_completion_json_mode(self) -> None:
        mock_llama = MagicMock()
        mock_llama.n_ctx.return_value = 4096
        mock_llama.create_chat_completion.return_value = {
            "choices": [{"message": {"content": '{"answer":"hi"}'}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 4},
        }
        with patch(
            "ai_runtime.services.local_generation_llama_cpp._get_llama",
            new_callable=AsyncMock,
            return_value=mock_llama,
        ):
            raw, inp, out = await LlamaCppLocalGenerationService().generate(
                system_prompt="Reply in JSON",
                human_message="hello",
                max_tokens=32,
                temperature=0.0,
                output_format="json",
            )
        assert raw == '{"answer":"hi"}'
        assert inp == 10
        assert out == 4
        call_kwargs = mock_llama.create_chat_completion.call_args.kwargs
        assert call_kwargs["response_format"] == {"type": "json_object"}

    @pytest.mark.asyncio
    async def test_llama_cpp_truncates_long_prompt_via_create_completion(self) -> None:
        mock_llama = MagicMock()
        mock_llama.chat_handler = None
        mock_llama._chat_handlers = {}
        mock_llama.chat_format = "chatml"
        mock_llama.verbose = False
        mock_llama.n_ctx.return_value = 4096
        mock_llama.tokenize.return_value = list(range(10))
        mock_llama.create_completion.return_value = {
            "choices": [{"text": '{"answer":"trimmed"}'}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 3},
        }

        mock_formatter = MagicMock()
        mock_formatter.return_value = MagicMock(
            prompt="long prompt",
            stop="</s>",
            added_special=True,
        )
        mock_handler = MagicMock()
        mock_handler.__closure__ = (type("Cell", (), {"cell_contents": mock_formatter})(),)

        with (
            patch(
                "ai_runtime.services.local_generation_llama_cpp._get_llama",
                new_callable=AsyncMock,
                return_value=mock_llama,
            ),
            patch(
                "llama_cpp.llama_chat_format.get_chat_completion_handler",
                return_value=mock_handler,
            ),
            patch(
                "ai_runtime.services.local_generation_llama_cpp._json_grammar",
                return_value=MagicMock(),
            ),
            patch(
                "ai_runtime.services.local_generation_llama_cpp.get_settings",
                return_value=MagicMock(local_generation_max_input_tokens=6),
            ),
        ):
            raw, inp, out = await LlamaCppLocalGenerationService().generate(
                system_prompt="sys",
                human_message="user",
                max_tokens=32,
                temperature=0.0,
                output_format="json",
            )

        assert raw == '{"answer":"trimmed"}'
        assert inp == 4
        assert out == 3
        mock_llama.create_chat_completion.assert_not_called()
        mock_llama.create_completion.assert_called_once()
        assert mock_llama.create_completion.call_args.kwargs["prompt"] == list(range(4, 10))

    @pytest.mark.asyncio
    async def test_llama_cpp_reserves_output_tokens_when_truncating_to_context(self) -> None:
        mock_llama = MagicMock()
        mock_llama.chat_handler = None
        mock_llama._chat_handlers = {}
        mock_llama.chat_format = "chatml"
        mock_llama.verbose = False
        mock_llama.n_ctx.return_value = 4096
        mock_llama.tokenize.return_value = list(range(5000))
        mock_llama.create_completion.return_value = {
            "choices": [{"text": '{"answer":"trimmed"}'}],
            "usage": {"prompt_tokens": 3584, "completion_tokens": 3},
        }

        mock_formatter = MagicMock()
        mock_formatter.return_value = MagicMock(
            prompt="long prompt",
            stop="</s>",
            added_special=True,
        )
        mock_handler = MagicMock()
        mock_handler.__closure__ = (type("Cell", (), {"cell_contents": mock_formatter})(),)

        with (
            patch(
                "ai_runtime.services.local_generation_llama_cpp._get_llama",
                new_callable=AsyncMock,
                return_value=mock_llama,
            ),
            patch(
                "llama_cpp.llama_chat_format.get_chat_completion_handler",
                return_value=mock_handler,
            ),
            patch(
                "ai_runtime.services.local_generation_llama_cpp._json_grammar",
                return_value=MagicMock(),
            ),
            patch(
                "ai_runtime.services.local_generation_llama_cpp.get_settings",
                return_value=MagicMock(local_generation_max_input_tokens=4096),
            ),
        ):
            await LlamaCppLocalGenerationService().generate(
                system_prompt="sys",
                human_message="user",
                max_tokens=512,
                temperature=0.0,
                output_format="json",
            )

        mock_llama.create_chat_completion.assert_not_called()
        prompt = mock_llama.create_completion.call_args.kwargs["prompt"]
        assert len(prompt) == 3584
        assert prompt == list(range(1416, 5000))


class TestEffectiveMaxInputTokens:
    def test_reserves_output_tokens_within_context(self) -> None:
        assert effective_max_input_tokens(n_ctx=4096, max_input_tokens=4096, max_tokens=512) == 3584

    def test_honors_lower_configured_cap(self) -> None:
        assert effective_max_input_tokens(n_ctx=4096, max_input_tokens=2048, max_tokens=512) == 2048
