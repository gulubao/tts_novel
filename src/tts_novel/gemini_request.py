"""Shared Gemini TTS request construction."""

from google.genai import types

PERMISSIVE_SAFETY_SETTINGS = [
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
        threshold=types.HarmBlockThreshold.OFF,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        threshold=types.HarmBlockThreshold.OFF,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        threshold=types.HarmBlockThreshold.OFF,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        threshold=types.HarmBlockThreshold.OFF,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_CIVIC_INTEGRITY,
        threshold=types.HarmBlockThreshold.OFF,
    ),
]


def build_tts_generate_config(voice_name: str) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        safety_settings=PERMISSIVE_SAFETY_SETTINGS,
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=voice_name,
                ),
            ),
        ),
    )


def build_tts_inline_request(
    *,
    key: str,
    prompt: str,
    voice_name: str,
) -> dict:
    return {
        "contents": [{"parts": [{"text": prompt}], "role": "user"}],
        "metadata": {"key": key},
        "config": build_tts_generate_config(voice_name),
    }
