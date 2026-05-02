"""Thin wrapper around google-genai for Gemini TTS, with 429 backoff.

Raises ``tts_novel.backends.base.BlockedContentError`` on both Gemini block
surfaces so the composite ``FallbackBackend`` can route to a secondary
backend without importing anything Gemini-specific.
"""

import sys
import time
from datetime import datetime

from google import genai
from google.genai import errors

from tts_novel.backends.base import BlockedContentError
from tts_novel.config import (
    DEFAULT_TTS_MODEL,
    ClientSettings,
    load_gcloud_adc_client_settings_if_available,
)
from tts_novel.gemini_request import build_tts_generate_config
from tts_novel.google_auth import is_api_key_invalid_error

__all__ = ["BlockedContentError", "TTSClient"]


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


_RATE_LIMIT_ATTEMPTS = 8
_RATE_LIMIT_INITIAL_DELAY_S = 5.0
_RATE_LIMIT_MAX_DELAY_S = 120.0


class TTSClient:
    def __init__(self, settings: ClientSettings, model_id: str = DEFAULT_TTS_MODEL):
        self._model_id = model_id
        self._settings = settings
        self._api_key_fallback_settings = (
            load_gcloud_adc_client_settings_if_available() if settings.api_key else None
        )
        self._using_api_key_fallback = False
        self._client = self._build_client(settings)

    def _build_client(self, settings: ClientSettings):
        if settings.use_vertex:
            if settings.api_key:
                return genai.Client(vertexai=True, api_key=settings.api_key)
            return genai.Client(
                    vertexai=True,
                    project=settings.project,
                    location=settings.location,
                )
        return genai.Client(api_key=settings.api_key)

    def _switch_to_api_key_fallback(self) -> bool:
        if self._using_api_key_fallback or self._api_key_fallback_settings is None:
            return False
        fallback = self._api_key_fallback_settings
        print(
            f"[{_ts()}] [tts_client] API key invalid; switching to Vertex AI ADC "
            f"project={fallback.project} location={fallback.location}",
            file=sys.stderr,
            flush=True,
        )
        self._client = self._build_client(fallback)
        self._settings = fallback
        self._using_api_key_fallback = True
        return True

    def _call_with_backoff(self, prompt: str, voice_name: str) -> bytes:
        delay = _RATE_LIMIT_INITIAL_DELAY_S
        last_exc: Exception | None = None
        for attempt in range(1, _RATE_LIMIT_ATTEMPTS + 1):
            try:
                response = self._client.models.generate_content(
                    model=self._model_id,
                    contents=prompt,
                    config=build_tts_generate_config(voice_name),
                )
            except errors.ClientError as e:
                if is_api_key_invalid_error(e) and self._switch_to_api_key_fallback():
                    return self._call_with_backoff(prompt, voice_name)
                if getattr(e, "code", None) == 429 and attempt < _RATE_LIMIT_ATTEMPTS:
                    print(
                        f"[{_ts()}] [tts_client] 429 RESOURCE_EXHAUSTED on attempt {attempt}; "
                        f"sleeping {delay:.1f}s then retrying",
                        file=sys.stderr,
                        flush=True,
                    )
                    time.sleep(delay)
                    delay = min(delay * 2, _RATE_LIMIT_MAX_DELAY_S)
                    last_exc = e
                    continue
                raise
            if not response.candidates:
                raise BlockedContentError(
                    "TTS returned no candidates "
                    f"(prompt_feedback={getattr(response, 'prompt_feedback', None)}); "
                    "the request was blocked before generation."
                )
            candidate = response.candidates[0]
            if candidate.content is None or candidate.content.parts is None:
                raise BlockedContentError(
                    f"TTS produced no audio parts (finish_reason={candidate.finish_reason}); "
                    "narration of this chunk was blocked post-hoc."
                )
            return candidate.content.parts[0].inline_data.data
        assert last_exc is not None
        raise last_exc

    def synthesize(self, text: str, voice_name: str, style_preamble: str) -> bytes:
        prompt = style_preamble + text
        return self._call_with_backoff(prompt, voice_name)
