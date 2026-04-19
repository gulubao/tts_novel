from tts_novel.backends.base import BlockedContentError, SynthesisResult
from tts_novel.backends.fallback import FallbackBackend


class _FakeBackend:
    def __init__(self, name: str, *, pcm: bytes | None = None, raise_with: Exception | None = None):
        self.name = name
        self._pcm = pcm
        self._raise_with = raise_with
        self.calls: list[str] = []

    def synthesize(self, text: str) -> SynthesisResult:
        self.calls.append(text)
        if self._raise_with is not None:
            raise self._raise_with
        assert self._pcm is not None
        return SynthesisResult(pcm=self._pcm, backend=self.name, seconds=0.01)


def test_primary_success_skips_fallback():
    primary = _FakeBackend("gemini", pcm=b"\x00\x01")
    fallback = _FakeBackend("kokoro", pcm=b"\x02\x03")
    chain = FallbackBackend(primary=primary, fallback=fallback)

    result = chain.synthesize("hello")

    assert result.pcm == b"\x00\x01"
    assert result.backend == "gemini"
    assert result.fallback_reason is None
    assert primary.calls == ["hello"]
    assert fallback.calls == []


def test_blocked_content_error_routes_to_fallback_and_sets_reason():
    primary = _FakeBackend("gemini", raise_with=BlockedContentError("PROHIBITED_CONTENT"))
    fallback = _FakeBackend("kokoro", pcm=b"\x04\x05")
    chain = FallbackBackend(primary=primary, fallback=fallback)

    result = chain.synthesize("hello")

    assert result.pcm == b"\x04\x05"
    assert result.backend == "kokoro"
    assert result.fallback_reason == "PROHIBITED_CONTENT"
    assert primary.calls == ["hello"]
    assert fallback.calls == ["hello"]


def test_non_block_exception_propagates():
    primary = _FakeBackend("gemini", raise_with=RuntimeError("429 throttled"))
    fallback = _FakeBackend("kokoro", pcm=b"\x06\x07")
    chain = FallbackBackend(primary=primary, fallback=fallback)

    raised = False
    try:
        chain.synthesize("hello")
    except RuntimeError as e:
        raised = True
        assert "429" in str(e)
    assert raised is True
    assert fallback.calls == []


def test_fallback_reason_uses_first_line_of_message():
    primary = _FakeBackend(
        "gemini",
        raise_with=BlockedContentError("block_reason=PROHIBITED_CONTENT\n(second line)"),
    )
    fallback = _FakeBackend("kokoro", pcm=b"\x08\x09")
    chain = FallbackBackend(primary=primary, fallback=fallback)

    result = chain.synthesize("hello")

    assert result.fallback_reason == "block_reason=PROHIBITED_CONTENT"
