# RUN

## Install

```bash
uv sync
```

This creates `.venv` and installs `google-genai`, `ebooklib`, `beautifulsoup4`, `lxml`, `python-dotenv`, `kokoro`, `soundfile`. Kokoro also needs the system `espeak-ng` binary (`brew install espeak-ng` on macOS, `apt install espeak-ng` on Ubuntu). In `--backend local` mode `espeak-ng` is required from the first chunk; in `--backend auto` mode it is only needed when a fallback actually triggers.

## Environment

`.env` at the project root. Required only for `--backend auto` (default). Skip this section entirely if you will always run with `--backend local`.

### Mode A — Vertex AI (uses Google Cloud billing; preferred when you have GCP credits)

Recommended key-based setup:

```
GOOGLE_CLOUD_API_KEY=<your-vertex-ai-google-cloud-api-key>
```

This path does not require local `gcloud` login. The Google Cloud project behind the key must have billing enabled and the Vertex AI API enabled. For existing Google Cloud projects, use a Vertex AI-compatible Google Cloud API key; if the key cannot be bound to a service account under your organization policy, use the ADC setup below. When `GOOGLE_CLOUD_API_KEY` is set, it takes precedence over `USE_VERTEX`, `GOOGLE_CLOUD_PROJECT`, and `GOOGLE_CLOUD_LOCATION`.

ADC setup, used only when `GOOGLE_CLOUD_API_KEY` is absent:

```
USE_VERTEX=1
GOOGLE_CLOUD_PROJECT=<your-gcp-project-id>
GOOGLE_CLOUD_LOCATION=us-central1
```

Prerequisites:

```bash
brew install --cask google-cloud-sdk       # one-time; macOS
gcloud auth application-default login      # opens a browser; stores ADC locally
gcloud auth application-default set-quota-project <your-gcp-project-id>
gcloud services enable aiplatform.googleapis.com --project <your-gcp-project-id>
```

### Switching Google Cloud projects

To switch to a different Google Cloud project or account (e.g., to use a different billing account):

For key-based setup, replace `GOOGLE_CLOUD_API_KEY` with a key from the target Google Cloud project.

For ADC setup:

```bash
# 1. Sign in with the new account (opens browser)
gcloud auth login

# 2. Update application default credentials
gcloud auth application-default login

# 3. Set the new quota project
gcloud auth application-default set-quota-project <your-new-project-id>

# 4. Enable Vertex AI API on the new project
gcloud services enable aiplatform.googleapis.com --project <your-new-project-id>

# 5. Update .env with the new project ID
# Edit .env and change: GOOGLE_CLOUD_PROJECT=<your-new-project-id>
```

### Mode B — Gemini Developer API (uses AI Studio prepayment balance)

```
GEMINI_API_KEY=<your key>
```

Omit `USE_VERTEX` or set it to `0`. Also omit `GOOGLE_CLOUD_API_KEY`; a cloud key always selects Vertex AI.

## Convert EPUB to per-chapter WAVs and MP3s (default behaviour)

One WAV and one MP3 per eligible chapter (`chapter_000.wav` + `chapter_000.mp3`, `chapter_001.wav` + `chapter_001.mp3`, …) under `--output-dir`. Chapters whose WAV and MP3 already exist are both skipped, so the run is resumable if it's interrupted:

```bash
uv run python -m tts_novel.cli \
    --input <input_epub_file_path> \
    --output-dir <output_dir_path> \
    --voice Sulafat
```

## Convert a single chapter

Use `--chapter N` with the 0-based eligible index. Useful for re-runs, spot checks, or re-synthesizing a single chapter after editing it:

```bash
uv run python -m tts_novel.cli \
    --input <input_epub_file_path> \
    --output-dir <output_dir_path> \
    --chapter <chapter_index> \
    --voice Sulafat
```

## Run entirely on a local model (no Google credentials)

`--backend local` swaps Gemini out for Kokoro-82M. Google auth, network, and per-token costs are all bypassed; the trade-off is a smaller voice catalogue and slightly lower naturalness. Useful for offline runs or when Gemini policy keeps blocking the text you care about.

```bash
uv run python -m tts_novel.cli \
    --input <input_epub_file_path> \
    --output-dir <output_dir_path> \
    --backend local \
    --local-voice bf_emma
```

## CLI flags

| Flag | Default | Meaning |
|---|---|---|
| `--input` | required | Path to the EPUB file. |
| `--output-dir` | `./output` | Directory for per-chapter WAV files. |
| `--cache-dir` | `<output-dir>/_pcm_cache` | Directory for per-chunk raw PCM cache. |
| `--backend` | `auto` | `auto` = Gemini TTS with local Kokoro-82M fallback on a content-policy block; `local` = Kokoro-82M only (no Google API calls or authentication required). |
| `--voice` | `Sulafat` | Prebuilt voice name used by Gemini TTS (ignored when `--backend local`). |
| `--style-preamble` | British RP female narration instruction | Prepended to each Gemini synthesis prompt (ignored when `--backend local`). |
| `--chapter` | all | Synthesize only the chapter at this 0-based eligible index. |
| `--min-chapter-chars` | `2000` | Discards short EPUB items (cover, TOC, dedication). |
| `--max-chars-per-chunk` | `200` | Maximum characters per TTS request (reduced from 2500 to improve Gemini TTS quality consistency on long passages). |
| `--no-combine` | off | Skip the final step that produces the combined `<book-stem>.wav` and `<book-stem>.mp3`. Ignored when `--chapter N` is set. |
| `--local-voice` | `bf_emma` | Kokoro voice id (British female). Used in `auto` fallback and `local` mode. |
| `--local-lang-code` | `b` | Kokoro language code (`b` = British English, `a` = American English). |
| `--mp3-quality` | `0.0` | MP3 compression level in [0.0, 0.9]. 0.0 = highest quality (~73 kbps VBR, default), 0.5 = balanced (~40 kbps), 0.8 = smallest (~33 kbps). |
| `--tts-model` | `gemini-2.5-flash-preview-tts` | Gemini TTS model ID. Choices: `gemini-2.5-flash-preview-tts` (default, $0.50/$10.00 per 1M input/output tokens) or `gemini-3.1-flash-tts-preview` ($1.00/$20.00, higher quality at 2x cost). Ignored when `--backend local`. |

## Local-only mode (no Google account, no network, no cost)

Pass `--backend local` to run entirely on Kokoro-82M (Apache-2.0, ~1 GB RAM, CPU-only). The model loads on first chunk, then stays resident for the rest of the run. The `.env` file, Vertex AI, `GOOGLE_CLOUD_API_KEY`, and `GEMINI_API_KEY` are all ignored. Voice and style preamble settings are Gemini-only and have no effect in this mode; use `--local-voice` to switch Kokoro voices.

Prerequisite on macOS: `brew install espeak-ng` (Kokoro's phonemizer shells out to this binary for out-of-vocabulary graphemes).

## Main pipeline (execution order)

1. `tts_novel.epub_reader.read_epub` — parses the EPUB, yields ordered non-empty document items as `Chapter(index, title, text)`.
2. `tts_novel.pipeline.select_chapters` — filters out items shorter than `min_chapter_chars` to produce the eligible list; `--chapter N` picks one element of that list.
3. `tts_novel.backends.build_backend` — constructs the synthesis backend dictated by `--backend`: `auto` builds `FallbackBackend(GeminiBackend, KokoroBackend)` (Gemini client settings loaded from `.env`, key-based Vertex AI, or ADC here, so auth errors surface up-front); `local` builds `KokoroBackend` alone.
4. For each eligible chapter:
   - If `<output-dir>/chapter_<NNN>.wav` already exists, skip the chapter entirely.
   - Otherwise, `tts_novel.text_chunker.chunk_text` groups paragraphs into chunks ≤ `max_chars_per_chunk` (default: 200 chars, reduced from 2500 for improved Gemini TTS quality consistency); oversized paragraphs fall back to sentence splits and then word-level splits when necessary to preserve the hard limit.
   - For each chunk: if the PCM cache file exists, load it; otherwise call `backend.synthesize(chunk)` and cache the returned PCM. A `SynthesisResult.fallback_reason` that is not `None` indicates the primary backend (Gemini) blocked and the secondary (Kokoro) produced the audio; this is recorded as a `BlockedChunkRecord` for the summary.
   - `tts_novel.wav_writer.concat_pcm` + `write_wav` produce the chapter WAV (24 kHz mono 16-bit).

## Output layout

```
<output-dir>/
├── <book-stem>.wav                  # combined single-file audiobook (produced after all chapters finish)
├── <book-stem>.mp3                  # combined single-file audiobook MP3 (produced after all chapters finish)
├── chapter_000.wav                  # first eligible chapter WAV
├── chapter_000.mp3                  # first eligible chapter MP3
├── chapter_001.wav
├── chapter_001.mp3
├── ...
└── _pcm_cache/
    ├── ch004_c000.pcm               # raw PCM per (doc_index, chunk_index)
    ├── ch004_c001.pcm
    └── ...
```

The combined `<book-stem>.wav` and `<book-stem>.mp3` are written automatically after every chapter WAV and MP3 are present. They are skipped when any chapter file is missing, when the combined file already exists, when `--chapter N` selected a single chapter, or when `--no-combine` was passed. Deleting the combined files and re-running the CLI regenerates them from the existing chapter files without any API calls.

Deleting any `chapter_NNN.wav` forces that chapter to be re-stitched from the PCM cache. Deleting a `.pcm` file forces that chunk to be re-synthesized via the API on the next run.
