"""Backward compatibility re-exports from audio_writer."""

from tts_novel.audio_writer import (
    concat_pcm,
    duration_seconds,
    write_mp3,
    write_wav,
)

__all__ = ["write_wav", "write_mp3", "concat_pcm", "duration_seconds"]
