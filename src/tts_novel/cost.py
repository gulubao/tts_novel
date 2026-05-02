"""Gemini TTS cost estimation.

Pricing rates are keyed by model ID via ``tts_novel.config.TTS_MODELS``.
Default rates match ``gemini-2.5-flash-preview-tts``:

* Text input: ``$0.50`` per ``1,000,000`` tokens.
* Audio output: ``$10.00`` per ``1,000,000`` tokens.
* Audio output produces ``25`` tokens per second of 24 kHz mono audio.

Token counts are estimated from characters using Google's published heuristic
of ``4`` characters per text token. Results are planning-grade approximations;
the authoritative record is the Cloud Billing invoice.

Batch-mode pricing (50% discount) is not applied here because this pipeline
issues synchronous ``generate_content`` requests only.
"""

from dataclasses import dataclass

from tts_novel.config import DEFAULT_TTS_MODEL, TTS_MODELS

CHARS_PER_TEXT_TOKEN = 4
AUDIO_TOKENS_PER_SECOND = 25
APPROX_CHARS_PER_AUDIO_SECOND = 15.0


@dataclass(frozen=True)
class CostEstimate:
    input_chars: int
    input_tokens: int
    audio_seconds: float
    audio_tokens: int
    input_usd: float
    output_usd: float
    total_usd: float


def _rates(model: str) -> tuple[float, float]:
    entry = TTS_MODELS.get(model)
    if entry is None:
        raise ValueError(f"unknown TTS model {model!r}; choose from {sorted(TTS_MODELS)}")
    return entry["input_usd_per_1m"], entry["audio_usd_per_1m"]


def estimate_input_tokens(input_chars: int) -> int:
    return (input_chars + CHARS_PER_TEXT_TOKEN - 1) // CHARS_PER_TEXT_TOKEN


def estimate_audio_tokens(audio_seconds: float) -> int:
    return int(audio_seconds * AUDIO_TOKENS_PER_SECOND + 0.5)


def estimate(
    input_chars: int,
    audio_seconds: float,
    model: str = DEFAULT_TTS_MODEL,
) -> CostEstimate:
    input_price, audio_price = _rates(model)
    input_tokens = estimate_input_tokens(input_chars)
    audio_tokens = estimate_audio_tokens(audio_seconds)
    input_usd = input_tokens * input_price / 1_000_000
    output_usd = audio_tokens * audio_price / 1_000_000
    return CostEstimate(
        input_chars=input_chars,
        input_tokens=input_tokens,
        audio_seconds=audio_seconds,
        audio_tokens=audio_tokens,
        input_usd=input_usd,
        output_usd=output_usd,
        total_usd=input_usd + output_usd,
    )


def estimate_from_text_only(
    input_chars: int,
    model: str = DEFAULT_TTS_MODEL,
) -> CostEstimate:
    """Planning-grade estimate when audio has not been synthesized yet.

    Uses ``APPROX_CHARS_PER_AUDIO_SECOND`` (empirical on British RP audiobook
    narration) to project audio seconds from input chars. The audio component
    dominates the total, so this heuristic is the largest source of error.
    """
    projected_audio_seconds = input_chars / APPROX_CHARS_PER_AUDIO_SECOND
    return estimate(input_chars, projected_audio_seconds, model=model)
