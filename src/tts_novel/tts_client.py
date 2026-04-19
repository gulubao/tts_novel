"""Thin wrapper around google-genai for Gemini TTS, with 429 backoff.

Raises ``tts_novel.backends.base.BlockedContentError`` on both Gemini block
surfaces so the composite ``FallbackBackend`` can route to a secondary
backend without importing anything Gemini-specific.
"""

import sys
import time
from datetime import datetime

from google import genai
from google.genai import errors, types

from tts_novel.backends.base import BlockedContentError
from tts_novel.config import MODEL_ID, ClientSettings

__all__ = ["BlockedContentError", "TTSClient"]


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


_PERMISSIVE_SAFETY_SETTINGS = [
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
        threshold=types.HarmBlockThreshold.OFF,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        threshold=types.HarmBlockThreshold.OFF,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        threshold=types.HarmBlockThreshold.OFF,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        threshold=types.HarmBlockThreshold.OFF,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_CIVIC_INTEGRITY,
        threshold=types.HarmBlockThreshold.OFF,
    ),
]


_RATE_LIMIT_ATTEMPTS = 8
_RATE_LIMIT_INITIAL_DELAY_S = 5.0
_RATE_LIMIT_MAX_DELAY_S = 120.0


class TTSClient:
    def __init__(self, settings: ClientSettings):
        if settings.use_vertex:
            self._client = genai.Client(
                vertexai=True,
                project=settings.project,
                location=settings.location,
            )
        else:
            self._client = genai.Client(api_key=settings.api_key)

    def _call_with_backoff(self, prompt: str, voice_name: str) -> bytes:
        delay = _RATE_LIMIT_INITIAL_DELAY_S
        last_exc: Exception | None = None
        for attempt in range(1, _RATE_LIMIT_ATTEMPTS + 1):
            try:
                response = self._client.models.generate_content(
                    model=MODEL_ID,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        safety_settings=_PERMISSIVE_SAFETY_SETTINGS,
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name=voice_name,
                                ),
                            ),
                        ),
                    ),
                )
            except errors.ClientError as e:
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
