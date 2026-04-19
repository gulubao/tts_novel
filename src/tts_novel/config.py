"""Runtime constants and client-settings loader."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

MODEL_ID = "gemini-3.1-flash-tts-preview"
SAMPLE_RATE_HZ = 24000
SAMPLE_WIDTH_BYTES = 2
CHANNELS = 1

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
    use_vertex = os.environ.get("USE_VERTEX", "").strip().lower() in ("1", "true", "yes")
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
