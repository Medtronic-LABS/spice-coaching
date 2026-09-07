"""Google Gemini provider adapter (google-genai unified SDK).

Supports both Vertex AI (service account via Application Default Credentials)
and the Gemini Developer API (API key) — selected at construction time.
The new SDK exposes a native async surface via `client.aio.models.*`, so we
no longer need `asyncio.to_thread` wrappers.

Multimodal: VISION_EXTRACTION sends one or more `types.Part.from_bytes`
parts alongside the human message text. The system_prompt remains a
`system_instruction` (passed via GenerateContentConfig).
"""

from __future__ import annotations

import inspect
import logging

from google import genai
from google.genai import types
from google.oauth2 import service_account

from ai_runtime.providers.base import BaseProvider, ProviderImage

logger = logging.getLogger(__name__)

_TRANSCRIPTION_TEMPERATURE = 0.0

# Gemini's documented audio MIME types use audio/mp3 (not audio/mpeg) and
# audio/wav (not audio/x-wav). Aliases are accepted inbound but must be
# normalized before Part.from_bytes or generate_content returns 400.
_GEMINI_AUDIO_MIME_ALIASES: dict[str, str] = {
    "audio/mpeg": "audio/mp3",
    "audio/x-wav": "audio/wav",
}


def _normalize_gemini_media_mime(mime_type: str) -> str:
    """Return the Gemini-canonical MIME for inline media parts."""
    lowered = mime_type.lower()
    return _GEMINI_AUDIO_MIME_ALIASES.get(lowered, lowered)


class GoogleProvider(BaseProvider):
    """Adapter over the `google-genai` unified SDK.

    Construct with one of:
    - `use_vertex=True` + `project` (and optional `location`); auth is ADC,
      typically via GOOGLE_APPLICATION_CREDENTIALS pointing at a service-
      account JSON.
    - `api_key=<gemini-developer-api-key>` for the legacy Developer API.

    Tests inject a `client` directly to bypass authentication entirely.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        use_vertex: bool = False,
        project: str | None = None,
        location: str | None = None,
        service_account_info: dict | None = None,
        client: genai.Client | None = None,
        embedding_dimension: int | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        http_options = None
        if timeout_seconds is not None:
            http_options = types.HttpOptions(timeout=int(timeout_seconds * 1000))

        if client is not None:
            self._client = client
        elif use_vertex or service_account_info:
            # When service_account_info is supplied we force Vertex mode and
            # build credentials from the dict in-process; otherwise the SDK
            # falls back to Application Default Credentials.
            actual_project = project
            credentials = None
            if service_account_info:
                credentials = service_account.Credentials.from_service_account_info(
                    service_account_info
                ).with_scopes(["https://www.googleapis.com/auth/cloud-platform"])
                if not actual_project:
                    actual_project = service_account_info.get("project_id")
            if not actual_project:
                raise ValueError("Vertex AI mode requires a project id")
            self._client = genai.Client(
                vertexai=True,
                project=actual_project,
                location=location or "us-central1",
                credentials=credentials,
                http_options=http_options,
            )
        else:
            if not api_key or api_key == "default=key":
                raise ValueError(
                    "Developer API mode requires a real api_key (or pass use_vertex=True with a project)"
                )
            self._client = genai.Client(api_key=api_key, http_options=http_options)
        self._embedding_dimension = embedding_dimension

    async def generate(
        self,
        system_prompt: str,
        human_message: str,
        model: str,
        max_tokens: int,
        temperature: float,
        images: list[ProviderImage] | None = None,
        output_format: str = "json",
        json_root: str = "object",
    ) -> tuple[str, int, int]:
        """Call Gemini and return (raw_text, input_tokens, output_tokens)."""
        contents: list[str | types.Part] = [human_message]
        for img in images or []:
            contents.append(types.Part.from_bytes(data=img.data, mime_type=img.mime_type))

        # Gemini 2.5 series uses "thinking" tokens that count against
        # max_output_tokens. The default budget on Vertex eats most of a
        # 2048-token cap (~1980 thinking + ~70 visible output → truncated
        # JSON every time). Setting thinking_budget=128 caps reasoning at a
        # small fixed value, leaving the rest of max_output_tokens free for
        # the actual JSON output. (0 is rejected by gemini-2.5-flash; only
        # 2.5-pro and 2.5-flash-lite allow it.)
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            max_output_tokens=max_tokens,
            temperature=temperature,
            response_mime_type="application/json" if output_format == "json" else "text/plain",
            thinking_config=types.ThinkingConfig(thinking_budget=128),
        )
        response = await self._client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )
        raw_text = response.text or ""
        input_tok = 0
        output_tok = 0
        usage = getattr(response, "usage_metadata", None)
        if usage is not None:
            input_tok = getattr(usage, "prompt_token_count", 0) or 0
            output_tok = getattr(usage, "candidates_token_count", 0) or 0
        return raw_text, input_tok, output_tok

    async def embed(self, texts: list[str], model: str) -> list[list[float]]:
        """Return embedding vectors for the given texts."""
        config_kwargs: dict = {"task_type": "RETRIEVAL_DOCUMENT"}
        if self._embedding_dimension is not None:
            config_kwargs["output_dimensionality"] = self._embedding_dimension
        config = types.EmbedContentConfig(**config_kwargs)
        response = await self._client.aio.models.embed_content(
            model=model,
            contents=texts,
            config=config,
        )
        return [list(e.values) for e in response.embeddings]

    async def transcribe_media(self, media_bytes: bytes, mime_type: str, model: str) -> str:
        """Transcribe speech from audio/video bytes via Gemini."""
        if not media_bytes:
            raise ValueError("media payload is empty")
        gemini_mime = _normalize_gemini_media_mime(mime_type)
        system_instruction = (
            "Transcribe the spoken content verbatim. "
            "Do not summarize. Preserve original language and wording."
        )
        prompt_text = "Provide only the transcript text."
        media_part = types.Part.from_bytes(data=media_bytes, mime_type=gemini_mime)
        inline = getattr(media_part, "inline_data", None)
        part_mime = getattr(inline, "mime_type", None) if inline is not None else None
        part_data_len = len(getattr(inline, "data", b"") or b"") if inline is not None else 0
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="text/plain",
            temperature=_TRANSCRIPTION_TEMPERATURE,
        )
        logger.info(
            "Gemini generate_content transcribe request model=%s mime_type=%s "
            "gemini_mime=%s part_mime=%s media_bytes=%d part_data_len=%d "
            "prompt=%r response_mime_type=%s temperature=%s system_instruction_len=%d",
            model,
            mime_type,
            gemini_mime,
            part_mime,
            len(media_bytes),
            part_data_len,
            prompt_text,
            config.response_mime_type,
            config.temperature,
            len(system_instruction),
        )
        try:
            response = await self._client.aio.models.generate_content(
                model=model,
                contents=[prompt_text, media_part],
                config=config,
            )
        except Exception:
            logger.exception(
                "Gemini generate_content transcribe failed model=%s mime_type=%s "
                "gemini_mime=%s part_mime=%s media_bytes=%d",
                model,
                mime_type,
                gemini_mime,
                part_mime,
                len(media_bytes),
            )
            raise
        text = (response.text or "").strip()
        usage = getattr(response, "usage_metadata", None)
        input_tok = getattr(usage, "prompt_token_count", None) if usage is not None else None
        output_tok = getattr(usage, "candidates_token_count", None) if usage is not None else None
        candidates = getattr(response, "candidates", None) or []
        finish_reason = None
        if candidates:
            finish_reason = getattr(candidates[0], "finish_reason", None)
        logger.info(
            "Gemini generate_content transcribe response model=%s text_len=%d "
            "input_tokens=%s output_tokens=%s finish_reason=%s",
            model,
            len(text),
            input_tok,
            output_tok,
            finish_reason,
        )
        return text

    async def aclose(self) -> None:
        close = getattr(self._client, "close", None)
        if close is None:
            return
        if inspect.iscoroutinefunction(close):
            await close()
        else:
            close()
