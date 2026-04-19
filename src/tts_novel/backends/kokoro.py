"""Local Kokoro-82M backend.

Apache-2.0 model, runs on CPU (~1 GB RAM, no GPU). Matches the Gemini audio
format exactly (24 kHz mono 16-bit PCM), so WAV stitching is seamless across
mixed-backend chapters. Model load is deferred to the first ``synthesize``
call; callers that never trigger it pay no import cost.
"""

import sys
import time
from datetime import datetime

import numpy as np

from tts_novel.backends.base import SynthesisResult
from tts_novel.config import CHANNELS, SAMPLE_RATE_HZ, SAMPLE_WIDTH_BYTES


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class KokoroBackend:
    name = "kokoro"

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

    def synthesize(self, text: str) -> SynthesisResult:
        self._ensure_loaded()
        assert self._pipeline is not None
        t0 = time.monotonic()
        segments = list(self._pipeline(text, voice=self._voice))
        if not segments:
            raise RuntimeError("Kokoro returned no audio segments for chunk")
        audio = np.concatenate([seg for _, _, seg in segments])
        pcm = (audio * 32767).clip(-32768, 32767).astype(np.int16).tobytes()
        assert CHANNELS == 1 and SAMPLE_RATE_HZ == 24000 and SAMPLE_WIDTH_BYTES == 2
        return SynthesisResult(pcm=pcm, backend=self.name, seconds=time.monotonic() - t0)
