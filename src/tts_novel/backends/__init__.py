"""TTS backend strategies and composites.

Public surface:

* ``TTSBackend`` — the Protocol all backends satisfy.
* ``SynthesisResult`` — the value returned from every ``synthesize`` call.
* ``BlockedContentError`` — transition signal for ``FallbackBackend``.
* ``GeminiBackend``, ``KokoroBackend`` — concrete backends.
* ``FallbackBackend`` — primary→fallback composite.
* ``build_backend`` — factory keyed on ``backend_mode``.
"""

from typing import Literal

from tts_novel.backends.base import (
    BlockedContentError,
    SynthesisResult,
    TTSBackend,
)
from tts_novel.backends.fallback import FallbackBackend
from tts_novel.backends.gemini import GeminiBackend
from tts_novel.backends.kokoro import KokoroBackend
from tts_novel.config import load_client_settings
from tts_novel.tts_client import TTSClient

BackendMode = Literal["auto", "local"]

__all__ = [
    "BackendMode",
    "BlockedContentError",
    "FallbackBackend",
    "GeminiBackend",
    "KokoroBackend",
    "SynthesisResult",
    "TTSBackend",
    "build_backend",
]


def build_backend(
    mode: BackendMode,
    *,
    voice: str,
    style_preamble: str,
    local_voice: str,
    local_lang_code: str,
) -> TTSBackend:
    """Construct the backend dictated by ``mode``.

    ``auto`` builds ``FallbackBackend(GeminiBackend, KokoroBackend)``; Gemini
    client settings (``.env`` / ADC) are loaded eagerly so auth problems
    surface before any chunk work starts.

    ``local`` builds ``KokoroBackend`` alone; no Google credentials are read.
    """
    kokoro = KokoroBackend(lang_code=local_lang_code, voice=local_voice)
    if mode == "local":
        return kokoro
    if mode == "auto":
        client = TTSClient(load_client_settings())
        gemini = GeminiBackend(client, voice=voice, style_preamble=style_preamble)
        return FallbackBackend(primary=gemini, fallback=kokoro)
    raise ValueError(f"unknown backend mode: {mode!r}")
