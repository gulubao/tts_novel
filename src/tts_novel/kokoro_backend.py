"""Local TTS backend using Kokoro-82M.

Used as a fallback when Gemini refuses a chunk under its PROHIBITED_CONTENT
policy. Output format matches the Gemini path exactly: 24 kHz mono 16-bit PCM
bytes, suitable for the existing `wav_writer.concat_pcm` + `write_wav`.
"""

import sys
from datetime import datetime

import numpy as np

from tts_novel.config import CHANNELS, SAMPLE_RATE_HZ, SAMPLE_WIDTH_BYTES


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class KokoroBackend:
    """Lazy-loaded Kokoro pipeline.

    Construction is cheap; the model is loaded on first `synthesize()` call
    so callers that never actually trigger the fallback pay no import cost.
    """

    def __init__(self, lang_code: str = "b", voice: str = "bf_emma"):
        self._lang_code = lang_code
        self._voice = voice
        self._pipeline = None

    def _ensure_loaded(self) -> None:
        if self._pipeline is not None:
            return
        print(
            f"[{_ts()}] [kokoro] loading model (lang={self._lang_code}, voice={self._voice})",
            file=sys.stderr,
            flush=True,
        )
        from kokoro import KPipeline  # heavy import deferred to first use

        self._pipeline = KPipeline(
            lang_code=self._lang_code,
            repo_id="hexgrad/Kokoro-82M",
        )

    def synthesize(self, text: str) -> bytes:
        self._ensure_loaded()
        assert self._pipeline is not None
        segments = list(self._pipeline(text, voice=self._voice))
        if not segments:
            raise RuntimeError("Kokoro returned no audio segments for chunk")
        audio = np.concatenate([seg for _, _, seg in segments])
        pcm = (audio * 32767).clip(-32768, 32767).astype(np.int16).tobytes()
        assert CHANNELS == 1 and SAMPLE_RATE_HZ == 24000 and SAMPLE_WIDTH_BYTES == 2
        return pcm
