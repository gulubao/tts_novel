# INSTALL

## Environment

```bash
uv sync
```

This creates `.venv` and installs the Python dependencies from `pyproject.toml`.

## Google Credentials

Default batch mode uses Gemini Developer API:

```bash
GEMINI_API_KEY=<your key>
```

If this key later fails with `API_KEY_INVALID`, the default batch command can fall back to Vertex AI realtime synthesis when ADC exists:

```bash
GOOGLE_CLOUD_PROJECT=<your-gcp-project-id>
GOOGLE_CLOUD_LOCATION=us-central1
gcloud auth application-default login
```

Those fallback chunks use realtime Vertex AI billing, not Gemini Batch API discounted billing.

Vertex AI credentials are supported for realtime mode:

```bash
GOOGLE_CLOUD_API_KEY=<your-vertex-ai-google-cloud-api-key>
```

or:

```bash
USE_VERTEX=1
GOOGLE_CLOUD_PROJECT=<your-gcp-project-id>
GOOGLE_CLOUD_LOCATION=us-central1
```

Run Vertex AI credentials with:

```bash
uv run python -m tts_novel.cli --input <book.epub> --synthesis-mode realtime
```

## Local Fallback

Kokoro needs `espeak-ng`:

```bash
brew install espeak-ng
```

On Ubuntu:

```bash
sudo apt install espeak-ng
```
