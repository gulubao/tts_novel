"""WAV writer and PCM concatenation."""

import wave
from pathlib import Path

from tts_novel.config import CHANNELS, SAMPLE_RATE_HZ, SAMPLE_WIDTH_BYTES


def write_wav(path: Path, pcm: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH_BYTES)
        wf.setframerate(SAMPLE_RATE_HZ)
        wf.writeframes(pcm)


def concat_pcm(parts: list[bytes]) -> bytes:
    return b"".join(parts)


def duration_seconds(pcm_byte_length: int) -> float:
    return pcm_byte_length / (SAMPLE_RATE_HZ * SAMPLE_WIDTH_BYTES * CHANNELS)
