"""Gemini TTS cost estimation.

Pricing rates reflect the public tariff for ``gemini-3.1-flash-tts-preview``
(see ``tts_novel.config.MODEL_ID``) on both Vertex AI and the Gemini Developer
API as of 2026-04:

* Text input: ``$1.00`` per ``1,000,000`` tokens.
* Audio output: ``$20.00`` per ``1,000,000`` tokens.
* Audio output produces ``25`` tokens per second of 24 kHz mono audio.

Token counts are estimated from characters using Google's published heuristic
of ``4`` characters per text token. Results are planning-grade approximations;
the authoritative record is the Cloud Billing invoice.

Batch-mode pricing (``$0.50`` / ``$10.00`` per 1M tokens) is not applied here
because this pipeline issues synchronous ``generate_content`` requests only.
"""

from dataclasses import dataclass

TEXT_INPUT_USD_PER_1M_TOKENS = 1.0
AUDIO_OUTPUT_USD_PER_1M_TOKENS = 20.0
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


def estimate_input_tokens(input_chars: int) -> int:
    return (input_chars + CHARS_PER_TEXT_TOKEN - 1) // CHARS_PER_TEXT_TOKEN


def estimate_audio_tokens(audio_seconds: float) -> int:
    return int(audio_seconds * AUDIO_TOKENS_PER_SECOND + 0.5)


def estimate(input_chars: int, audio_seconds: float) -> CostEstimate:
    input_tokens = estimate_input_tokens(input_chars)
    audio_tokens = estimate_audio_tokens(audio_seconds)
    input_usd = input_tokens * TEXT_INPUT_USD_PER_1M_TOKENS / 1_000_000
    output_usd = audio_tokens * AUDIO_OUTPUT_USD_PER_1M_TOKENS / 1_000_000
    return CostEstimate(
        input_chars=input_chars,
        input_tokens=input_tokens,
        audio_seconds=audio_seconds,
        audio_tokens=audio_tokens,
        input_usd=input_usd,
        output_usd=output_usd,
        total_usd=input_usd + output_usd,
    )


def estimate_from_text_only(input_chars: int) -> CostEstimate:
    """Planning-grade estimate when audio has not been synthesized yet.

    Uses ``APPROX_CHARS_PER_AUDIO_SECOND`` (empirical on British RP audiobook
    narration) to project audio seconds from input chars. The audio component
    dominates the total, so this heuristic is the largest source of error.
    """
    projected_audio_seconds = input_chars / APPROX_CHARS_PER_AUDIO_SECOND
    return estimate(input_chars, projected_audio_seconds)
