from tts_novel import config
from tts_novel.config import ClientSettings
from tts_novel.tts_client import TTSClient


def test_google_cloud_api_key_selects_vertex_without_project(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("GOOGLE_CLOUD_API_KEY", "cloud-key")
    monkeypatch.delenv("USE_VERTEX", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_LOCATION", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    settings = config.load_client_settings()

    assert settings.use_vertex is True
    assert settings.api_key == "cloud-key"
    assert settings.project is None
    assert settings.location == ""


def test_google_cloud_api_key_precedes_adc_project(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("GOOGLE_CLOUD_API_KEY", "cloud-key")
    monkeypatch.setenv("USE_VERTEX", "1")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "project-from-adc-path")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")

    settings = config.load_client_settings()

    assert settings.use_vertex is True
    assert settings.api_key == "cloud-key"
    assert settings.project is None
    assert settings.location == ""


def test_vertex_adc_path_remains_available_without_cloud_key(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.delenv("GOOGLE_CLOUD_API_KEY", raising=False)
    monkeypatch.setenv("USE_VERTEX", "1")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "adc-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")

    settings = config.load_client_settings()

    assert settings.use_vertex is True
    assert settings.api_key is None
    assert settings.project == "adc-project"
    assert settings.location == "us-central1"


def test_gemini_developer_api_path_remains_available(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.delenv("GOOGLE_CLOUD_API_KEY", raising=False)
    monkeypatch.delenv("USE_VERTEX", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")

    settings = config.load_client_settings()

    assert settings.use_vertex is False
    assert settings.api_key == "gemini-key"
    assert settings.project is None
    assert settings.location == ""


def test_tts_client_passes_vertex_key_without_project_location(monkeypatch):
    calls: list[dict[str, object]] = []

    class FakeClient:
        def __init__(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr("tts_novel.tts_client.genai.Client", FakeClient)

    TTSClient(
        ClientSettings(
            use_vertex=True,
            api_key="cloud-key",
            project=None,
            location="",
        )
    )

    assert calls == [{"vertexai": True, "api_key": "cloud-key"}]
