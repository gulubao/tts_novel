"""Tests for audio_writer module: WAV and MP3 encoding, streaming concatenation."""

import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from tts_novel.audio_writer import (
    combine_audio_files,
    concat_pcm,
    duration_seconds,
    write_mp3,
    write_wav,
)
from tts_novel.config import SAMPLE_RATE_HZ, SAMPLE_WIDTH_BYTES, CHANNELS


def _silence_pcm(seconds: float = 1.0) -> bytes:
    """Generate silence PCM for testing."""
    num_samples = int(seconds * SAMPLE_RATE_HZ)
    arr = np.zeros(num_samples, dtype=np.int16)
    return arr.tobytes()


def _speech_like_pcm(seconds: float = 1.0) -> bytes:
    """Generate speech-like PCM for testing (sine wave + noise)."""
    num_samples = int(seconds * SAMPLE_RATE_HZ)
    t = np.linspace(0, seconds, num_samples, False)
    sig = (np.sin(2 * np.pi * 200 * t) * 5000 + np.sin(2 * np.pi * 800 * t) * 3000).astype(np.int16)
    return sig.tobytes()


def test_write_wav_creates_valid_file() -> None:
    pcm = _silence_pcm(1.0)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = Path(f.name)

    try:
        write_wav(path, pcm)

        assert path.exists()
        info = sf.info(str(path))
        assert info.samplerate == SAMPLE_RATE_HZ
        assert info.channels == CHANNELS
        assert info.duration == 1.0
    finally:
        path.unlink(missing_ok=True)


def test_write_mp3_creates_valid_file() -> None:
    pcm = _silence_pcm(1.0)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        path = Path(f.name)

    try:
        write_mp3(path, pcm, mp3_quality=0.5)

        assert path.exists()
        info = sf.info(str(path))
        assert info.samplerate == SAMPLE_RATE_HZ
        assert info.channels == CHANNELS
        assert abs(info.duration - 1.0) < 0.01
    finally:
        path.unlink(missing_ok=True)


def test_write_mp3_quality_parameter_affects_size() -> None:
    pcm = _speech_like_pcm(5.0)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        high_q_path = Path(f.name)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        low_q_path = Path(f.name)

    try:
        write_mp3(high_q_path, pcm, mp3_quality=0.0)
        write_mp3(low_q_path, pcm, mp3_quality=0.8)

        assert high_q_path.exists()
        assert low_q_path.exists()
        assert high_q_path.stat().st_size > low_q_path.stat().st_size
    finally:
        high_q_path.unlink(missing_ok=True)
        low_q_path.unlink(missing_ok=True)


def test_concat_pcm_joins_bytes() -> None:
    a = b"abc"
    b = b"def"
    result = concat_pcm([a, b])
    assert result == b"abcdef"


def test_duration_seconds_calculates_correctly() -> None:
    pcm = _silence_pcm(2.5)
    result = duration_seconds(len(pcm))
    assert abs(result - 2.5) < 0.01


def test_combine_audio_files_wav() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        ch1 = tmpdir / "ch1.wav"
        ch2 = tmpdir / "ch2.wav"
        out = tmpdir / "combined.wav"

        write_wav(ch1, _silence_pcm(1.0))
        write_wav(ch2, _silence_pcm(2.0))

        combine_audio_files([ch1, ch2], out, format="wav")

        assert out.exists()
        info = sf.info(str(out))
        assert abs(info.duration - 3.0) < 0.01


def test_combine_audio_files_mp3() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        ch1 = tmpdir / "ch1.mp3"
        ch2 = tmpdir / "ch2.mp3"
        out = tmpdir / "combined.mp3"

        write_mp3(ch1, _silence_pcm(1.0), mp3_quality=0.5)
        write_mp3(ch2, _silence_pcm(2.0), mp3_quality=0.5)

        combine_audio_files([ch1, ch2], out, format="mp3", mp3_quality=0.5)

        assert out.exists()
        info = sf.info(str(out))
        assert abs(info.duration - 3.0) < 0.1


def test_combine_audio_files_unsupported_format_raises() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        ch = tmpdir / "ch.wav"
        out = tmpdir / "out.ogg"

        write_wav(ch, _silence_pcm(1.0))

        try:
            combine_audio_files([ch], out, format="ogg")
            assert False, "Expected ValueError"
        except ValueError as e:
            assert "Unsupported format" in str(e)
