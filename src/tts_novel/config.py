"""Runtime constants and client-settings loader."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

SAMPLE_RATE_HZ = 24000
SAMPLE_WIDTH_BYTES = 2
CHANNELS = 1

TTS_MODELS: dict[str, dict[str, float]] = {
    "gemini-2.5-flash-preview-tts": {
        "input_usd_per_1m": 0.50,
        "audio_usd_per_1m": 10.00,
    },
    "gemini-3.1-flash-tts-preview": {
        "input_usd_per_1m": 1.00,
        "audio_usd_per_1m": 20.00,
    },
}

DEFAULT_TTS_MODEL = "gemini-2.5-flash-preview-tts"

DEFAULT_VOICE = "Sulafat"

DEFAULT_STYLE_PREAMBLE = (
    "Narrate the text that follows as a British female audiobook narrator "
    "with a warm Received Pronunciation accent, at a calm and deliberate pace, "
    "with natural pauses between sentences. Do not speak these instructions. "
    "Begin narration at the line after 'TEXT:'.\n\nTEXT:\n"
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ClientSettings:
    use_vertex: bool
    api_key: str | None
    project: str | None
    location: str


def load_client_settings() -> ClientSettings:
    load_dotenv(PROJECT_ROOT / ".env")
    cloud_api_key = os.environ.get("GOOGLE_CLOUD_API_KEY", "").strip()
    if cloud_api_key:
        return ClientSettings(
            use_vertex=True,
            api_key=cloud_api_key,
            project=None,
            location="",
        )

    use_vertex = os.environ.get("USE_VERTEX", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if use_vertex:
        return ClientSettings(
            use_vertex=True,
            api_key=None,
            project=os.environ["GOOGLE_CLOUD_PROJECT"],
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
        )
    return ClientSettings(
        use_vertex=False,
        api_key=os.environ["GEMINI_API_KEY"],
        project=None,
        location="",
    )
