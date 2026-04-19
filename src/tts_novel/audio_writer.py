"""WAV and MP3 audio writers with streaming concatenation."""

import wave
from pathlib import Path
from typing import BinaryIO

import soundfile as sf

from tts_novel.config import CHANNELS, SAMPLE_RATE_HZ, SAMPLE_WIDTH_BYTES


def write_wav(path: Path, pcm: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH_BYTES)
        wf.setframerate(SAMPLE_RATE_HZ)
        wf.writeframes(pcm)


def write_mp3(path: Path, pcm: bytes, mp3_quality: float | None = None) -> None:
    """Encode PCM bytes to MP3 using soundfile's built-in encoder.

    Args:
        path: Output .mp3 file path.
        pcm: Raw PCM bytes (24 kHz mono 16-bit, as defined in config.py).
        mp3_quality: libsndfile compression level in [0.0, 0.9].
            0.0 = highest quality (~73 kbps VBR on speech),
            0.5 = balanced (~40 kbps),
            0.8 = smallest (~33 kbps).
            None = soundfile default (~48 kbps VBR).
    """
    import numpy as np

    path.parent.mkdir(parents=True, exist_ok=True)

    samples = np.frombuffer(pcm, dtype=np.int16)

    kwargs = {"format": "MP3", "subtype": "MPEG_LAYER_III"}
    if mp3_quality is not None:
        kwargs["compression_level"] = mp3_quality

    sf.write(str(path), samples, SAMPLE_RATE_HZ, **kwargs)


def concat_pcm(parts: list[bytes]) -> bytes:
    return b"".join(parts)


def duration_seconds(pcm_byte_length: int) -> float:
    return pcm_byte_length / (SAMPLE_RATE_HZ * SAMPLE_WIDTH_BYTES * CHANNELS)


def _combine_wavs_impl(wav_paths: list[Path], output_path: Path) -> None:
    """Stitch WAV files into a single WAV by copying raw frames."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as out:
        out.setnchannels(CHANNELS)
        out.setsampwidth(SAMPLE_WIDTH_BYTES)
        out.setframerate(SAMPLE_RATE_HZ)
        for wav_path in wav_paths:
            with wave.open(str(wav_path), "rb") as wf:
                if (
                    wf.getnchannels() != CHANNELS
                    or wf.getsampwidth() != SAMPLE_WIDTH_BYTES
                    or wf.getframerate() != SAMPLE_RATE_HZ
                ):
                    raise RuntimeError(
                        f"Chapter WAV {wav_path} has incompatible format; "
                        f"expected {CHANNELS}ch/{SAMPLE_WIDTH_BYTES}B/{SAMPLE_RATE_HZ}Hz"
                    )
                out.writeframes(wf.readframes(wf.getnframes()))


def _combine_mp3s_impl(mp3_paths: list[Path], output_path: Path, mp3_quality: float | None = None) -> None:
    """Stitch MP3 files by streaming decode-then-encode to avoid loading full book into memory.

    Reads each chapter MP3 in blocks and appends to a single MP3 output file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    block_size = 8192

    kwargs = {"format": "MP3", "subtype": "MPEG_LAYER_III"}
    if mp3_quality is not None:
        kwargs["compression_level"] = mp3_quality

    with sf.SoundFile(str(output_path), "w", samplerate=SAMPLE_RATE_HZ, channels=CHANNELS, **kwargs) as out:
        for mp3_path in mp3_paths:
            with sf.SoundFile(str(mp3_path), "r") as src:
                if src.samplerate != SAMPLE_RATE_HZ or src.channels != CHANNELS:
                    raise RuntimeError(
                        f"Chapter MP3 {mp3_path} has incompatible format; "
                        f"expected {CHANNELS}ch/{SAMPLE_RATE_HZ}Hz"
                    )
                while True:
                    block = src.read(block_size, dtype="int16")
                    if len(block) == 0:
                        break
                    out.write(block)


def combine_audio_files(
    audio_paths: list[Path],
    output_path: Path,
    format: str,
    mp3_quality: float | None = None,
) -> None:
    """Combine multiple audio files into one.

    Args:
        audio_paths: List of chapter audio files in order.
        output_path: Destination file path.
        format: Either 'wav' or 'mp3'.
        mp3_quality: libsndfile compression level, only used when format='mp3'.
    """
    if format == "wav":
        _combine_wavs_impl(audio_paths, output_path)
    elif format == "mp3":
        _combine_mp3s_impl(audio_paths, output_path, mp3_quality=mp3_quality)
    else:
        raise ValueError(f"Unsupported format: {format}")
