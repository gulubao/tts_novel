"""Backend strategy protocol and shared value types.

The pipeline depends on this module; concrete backends implement the
``TTSBackend`` protocol and return a ``SynthesisResult``. ``BlockedContentError``
is the canonical transition signal a composite such as ``FallbackBackend``
catches to route from primary to fallback.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class BlockedContentError(RuntimeError):
    """Raised when a backend refuses to synthesize a chunk.

    Used by ``tts_client.TTSClient`` for both Gemini block surfaces:

    * pre-submission: ``response.candidates is None`` with a
      ``prompt_feedback.block_reason`` such as ``PROHIBITED_CONTENT``;
    * post-generation: ``candidate.finish_reason == SAFETY`` with
      ``content.parts is None``.
    """


@dataclass(frozen=True)
class SynthesisResult:
    """Outcome of one ``backend.synthesize()`` call.

    ``backend`` is the ``name`` of the concrete backend that produced the PCM
    (for ``FallbackBackend`` this is the backend that actually returned audio,
    not the composite itself). ``fallback_reason`` is ``None`` on primary
    success and carries the primary's block message when a fallback occurred.
    """

    pcm: bytes
    backend: str
    seconds: float
    fallback_reason: str | None = None


@runtime_checkable
class TTSBackend(Protocol):
    """Minimal contract every concrete backend satisfies."""

    name: str

    def synthesize(self, text: str) -> SynthesisResult: ...
