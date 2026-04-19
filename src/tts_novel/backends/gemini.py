"""Gemini TTS backend.

Thin adapter that binds voice and style preamble to a ``TTSClient`` instance
and conforms to the ``TTSBackend`` protocol. ``BlockedContentError`` and 429
backoff stay inside ``tts_client.TTSClient``; this module is deliberately
stateless above the bound parameters.
"""

import time

from tts_novel.backends.base import SynthesisResult
from tts_novel.tts_client import TTSClient


class GeminiBackend:
    name = "gemini"

    def __init__(self, client: TTSClient, voice: str, style_preamble: str):
        self._client = client
        self._voice = voice
        self._style_preamble = style_preamble

    def synthesize(self, text: str) -> SynthesisResult:
        t0 = time.monotonic()
        pcm = self._client.synthesize(text, self._voice, self._style_preamble)
        return SynthesisResult(pcm=pcm, backend=self.name, seconds=time.monotonic() - t0)
