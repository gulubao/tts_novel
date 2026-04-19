# TTS Novel — turn an e-book into an audiobook

This is a tiny tool that takes an EPUB e-book and reads it using Google's Gemini text-to-speech model `gemini-3.1-flash-tts-preview`.

The default voice is **Sulafat**, english UK female voice, check https://docs.cloud.google.com/text-to-speech/docs/gemini-tts for more details about api configuration.

## One-time setup on Mac (about 10 minutes)

### 1.

```bash
brew install uv
brew install --cask google-cloud-sdk
```

If `brew` itself isn't installed yet, get it first from https://brew.sh — paste the single command from their front page.

### 2. Sign in to Google

```bash
gcloud auth login
gcloud auth application-default login
```

### 3. Enable the service on your Google Cloud project

Go to https://console.cloud.google.com and note your **Project ID** (shown at the top of the page). Then run:

```bash
gcloud auth application-default set-quota-project YOUR_PROJECT_ID
gcloud services enable aiplatform.googleapis.com --project YOUR_PROJECT_ID
```

Replace `YOUR_PROJECT_ID` with the one from the console.

### 4. Download this tool

```bash
cd ~/Documents
git clone <this-repo-url> tts_novel
cd tts_novel
```

Create a file called `.env` in that folder with these four lines (use your own Project ID):

```bash
touch .env
```

```.env
USE_VERTEX=1
GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
GOOGLE_CLOUD_LOCATION=us-central1
GEMINI_API_KEY=unused
```

### 5. Install the Python bits

```bash
uv sync
```

## Using it

### Turn a book into audio

Put your `.epub` file somewhere easy to find, then run (Mac example):

```bash
uv run python -m tts_novel.cli \
    --input "/path/to/your-book.epub" \
    --output-dir "./output"
```

It will go chapter by chapter. You'll see progress lines like:

```
chapter 003 doc=008 START (5 chunks, 11,320 chars)
  [chapter 003 doc=008] chunk 1/5 chars=2415 synth (7,603,200 bytes in 70.8s)
  ...
chapter 003 doc=008 DONE (34,037,760 pcm bytes, 709.1s audio) -> chapter_003.wav
```

Each chapter takes **about 5 minutes** to narrate. A whole novel typically takes **2–4 hours** and costs roughly **a few dollars** in Google credits.

**You can stop it and start it again later.** Finished chapters are skipped automatically, so you can leave it overnight, or pause and resume.

### Just one chapter

Handy for a preview or to re-do one chapter:

```bash
uv run python -m tts_novel.cli \
    --input "/path/to/your-book.epub" \
    --output-dir "./output" \
    --chapter 0
```

`--chapter 0` is the first chapter (prologues count), `--chapter 1` is the second, and so on.

### Try a different voice

```bash
uv run python -m tts_novel.cli \
    --input "/path/to/your-book.epub" \
    --output-dir "./output" \
    --voice Vindemiatrix
```

Female voices you can try: **Sulafat** (warm), **Vindemiatrix** (gentle), **Aoede** (breezy), **Leda** (youthful), **Kore** (firm), **Zephyr** (bright).

Male voices if you prefer: **Charon** (informative), **Puck** (upbeat), **Orus** (firm), **Fenrir** (excitable), **Algieba** (smooth), **Enceladus** (breathy).

## What it produces

- One `.wav` file per chapter, 24 kHz mono — good audio quality, not super compressed
- One combined `<book-name>.wav` with every chapter stitched together in order, produced automatically after all chapters are done (pass `--no-combine` to skip it)
- A `_pcm_cache/` folder with raw audio bits (you can delete this once everything's done; it's just for the "resume where I left off" feature)

WAV files are large — a whole novel is typically 1–2 GB for the combined file and a similar total across the per-chapter files. If you want smaller files, open a WAV in Apple's Music app (or use a tool like [Audacity](https://www.audacityteam.org/)) and export as MP3.