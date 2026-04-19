"""Composite backend: primary → fallback on ``BlockedContentError``.

Keeps the chunk loop in ``pipeline._synthesize_chapter`` free of
backend-specific branching. Any other exception from ``primary`` propagates
unchanged so rate limits, network errors, and the like surface at the caller.
"""

import sys
from datetime import datetime

from tts_novel.backends.base import (
    BlockedContentError,
    SynthesisResult,
    TTSBackend,
)


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class FallbackBackend:
    name = "fallback"

    def __init__(self, primary: TTSBackend, fallback: TTSBackend):
        self._primary = primary
        self._fallback = fallback

    def synthesize(self, text: str) -> SynthesisResult:
        try:
            return self._primary.synthesize(text)
        except BlockedContentError as e:
            reason = str(e).split("\n", 1)[0]
            print(
                f"[{_ts()}] [{self._primary.name}] blocked; routing to "
                f"{self._fallback.name}: {reason}",
                file=sys.stderr,
                flush=True,
            )
            result = self._fallback.synthesize(text)
            return SynthesisResult(
                pcm=result.pcm,
                backend=result.backend,
                seconds=result.seconds,
                fallback_reason=reason,
            )
