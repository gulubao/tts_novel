# RUN

## Install

```bash
uv sync
```

This creates `.venv` and installs `google-genai`, `ebooklib`, `beautifulsoup4`, `lxml`, `python-dotenv`.

## Environment

`.env` at the project root. Two authentication modes:

### Mode A — Vertex AI (uses Google Cloud billing; preferred when you have GCP credits)

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

### Mode B — Gemini Developer API (uses AI Studio prepayment balance)

```
GEMINI_API_KEY=<your key>
```

Omit `USE_VERTEX` or set it to `0`.

## Convert EPUB to per-chapter WAVs (default behaviour)

One WAV per eligible chapter (`chapter_000.wav`, `chapter_001.wav`, …) under `--output-dir`. Chapters whose WAV already exists are skipped, so the run is resumable if it's interrupted:

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

## CLI flags

| Flag | Default | Meaning |
|---|---|---|
| `--input` | required | Path to the EPUB file. |
| `--output-dir` | `./output` | Directory for per-chapter WAV files. |
| `--cache-dir` | `<output-dir>/_pcm_cache` | Directory for per-chunk raw PCM cache. |
| `--voice` | `Sulafat` | Prebuilt voice name used by Gemini TTS. |
| `--style-preamble` | British RP female narration instruction | Prepended to each synthesis prompt. |
| `--chapter` | all | Synthesize only the chapter at this 0-based eligible index. |
| `--min-chapter-chars` | `2000` | Discards short EPUB items (cover, TOC, dedication). |
| `--max-chars-per-chunk` | `2500` | Soft upper bound on characters per TTS request. |
| `--no-combine` | off | Skip the final step that produces the combined `<book-stem>.wav`. Ignored when `--chapter N` is set. |

## Logic unit tests

```bash
uv run python -m pytest tests -q
```

## Main pipeline (execution order)

1. `tts_novel.epub_reader.read_epub` — parses the EPUB, yields ordered non-empty document items as `Chapter(index, title, text)`.
2. `tts_novel.pipeline.select_chapters` — filters out items shorter than `min_chapter_chars` to produce the eligible list; `--chapter N` picks one element of that list.
3. For each eligible chapter:
   - If `<output-dir>/chapter_<NNN>.wav` already exists, skip the chapter entirely.
   - Otherwise, `tts_novel.text_chunker.chunk_text` groups paragraphs into chunks ≤ `max_chars_per_chunk`; oversized paragraphs fall back to sentence splits.
   - For each chunk: if the PCM cache file exists, load it; otherwise call `tts_novel.tts_client.TTSClient.synthesize` and cache the returned PCM.
   - `tts_novel.wav_writer.concat_pcm` + `write_wav` produce the chapter WAV (24 kHz mono 16-bit).

## Output layout

```
<output-dir>/
├── <book-stem>.wav                  # combined single-file audiobook (produced after all chapters finish)
├── chapter_000.wav                  # first eligible chapter
├── chapter_001.wav
├── ...
└── _pcm_cache/
    ├── ch004_c000.pcm               # raw PCM per (doc_index, chunk_index)
    ├── ch004_c001.pcm
    └── ...
```

The combined `<book-stem>.wav` is written automatically after every chapter WAV is present. It is skipped when any chapter WAV is missing, when the combined file already exists, when `--chapter N` selected a single chapter, or when `--no-combine` was passed. Deleting the combined WAV and re-running the CLI regenerates it from the existing chapter WAVs without any API calls.

Deleting any `chapter_NNN.wav` forces that chapter to be re-stitched from the PCM cache. Deleting a `.pcm` file forces that chunk to be re-synthesized via the API on the next run.
