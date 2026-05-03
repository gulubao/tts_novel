# TTS Novel — turn an e-book into an audiobook

This is a tiny tool that takes an EPUB e-book and reads it using Google's Gemini text-to-speech model `gemini-2.5-flash-preview-tts` by default. It submits missing chunks through Gemini Batch API one chapter at a time, then stitches chapter WAV and MP3 files. When Gemini refuses a passage under its content policy, the tool falls back automatically to a local Kokoro-82M voice so the narration has no silent gaps. You can also run fully on the local model with `--backend local` — no Google account needed.

The default Gemini voice is **Sulafat**, an English UK female voice; see https://docs.cloud.google.com/text-to-speech/docs/gemini-tts for the full list. The default local voice is **bf_emma** (British female).

**Output format:** The tool produces both WAV and MP3 files for each chapter and for the combined audiobook. MP3 files are roughly 10-15% the size of WAV files (e.g., a 12-minute chapter might be 20 MB as WAV, 2-3 MB as MP3 at the default quality setting).

## One-time setup on Mac (about 10 minutes)

### 1.

```bash
brew install uv
```

If `brew` itself isn't installed yet, get it first from https://brew.sh — paste the single command from their front page.

### 2. Download this tool

```bash
cd ~/Documents
git clone <this-repo-url> tts_novel
cd tts_novel
```

Create a file called `.env` in that folder:

```bash
touch .env
```

### 3. Configure Gemini credentials

Default batch mode requires a Gemini Developer API key:

```.env
GEMINI_API_KEY=your-gemini-api-key
```

For Vertex AI billing, use realtime mode with a Google Cloud API key. The Google Cloud project behind the key must have billing enabled and the Vertex AI API enabled:

```.env
GOOGLE_CLOUD_API_KEY=your-google-cloud-api-key
```

This key path does not require `gcloud` login. If you cannot use a Vertex AI-compatible Google Cloud API key, use ADC instead:

```bash
brew install --cask google-cloud-sdk
gcloud auth application-default login
gcloud auth application-default set-quota-project YOUR_PROJECT_ID
gcloud services enable aiplatform.googleapis.com --project YOUR_PROJECT_ID
```

Then use:

```.env
USE_VERTEX=1
GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
GOOGLE_CLOUD_LOCATION=us-central1
```

### 4. Install the Python bits

```bash
uv sync
```

### Switch to a different Google Cloud project

If you need to switch to another Google Cloud account or project (e.g., to use a different billing account):

With key-based setup, replace `GOOGLE_CLOUD_API_KEY` in `.env` with a key from the new project.

With ADC setup:

```bash
# 1. Sign in with the new account
gcloud auth login

# 2. Update application default credentials
gcloud auth application-default login

# 3. Set the new quota project
gcloud auth application-default set-quota-project YOUR_NEW_PROJECT_ID

# 4. Enable Vertex AI API on the new project
gcloud services enable aiplatform.googleapis.com --project YOUR_NEW_PROJECT_ID

# 5. Update your .env file with the new project ID
# Edit .env and change GOOGLE_CLOUD_PROJECT to your new project
```

## Using it

### Turn a book into audio

Put your `.epub` file somewhere easy to find, then run (Mac example):

```bash
uv run python -m tts_novel.cli \
    --input "/path/to/your-book.epub" \
    --output-dir "./output"
```

It will go chapter by chapter. Existing chapter WAV+MP3 pairs are skipped. You'll see progress lines like:

```
chapter 003 doc=008 START (57 chunks, 11,320 chars)
chapter 003 doc=008 BATCH (57 missing chunk(s), 1 job(s))
batch: submitted batches/123456 (57 request(s), tts-novel-ch003-part001-of-001)
  ...
chapter 003 doc=008 DONE (34,037,760 pcm bytes, 709.1s audio) -> chapter_003.wav, chapter_003.mp3
```

Batch jobs are asynchronous and priced at 50% of standard Gemini TTS rates. If the Developer API key fails with `API_KEY_INVALID` and ADC exists, cache-missing chunks switch to Vertex AI realtime synthesis; those fallback chunks use standard realtime billing. For Vertex AI realtime mode from the start, add `--synthesis-mode realtime`.

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

### Run without a Google account (fully local)

```bash
uv run python -m tts_novel.cli \
    --input "/path/to/your-book.epub" \
    --output-dir "./output" \
    --backend local
```

This uses Kokoro-82M, an Apache-2.0 local TTS model (~1 GB RAM, CPU-only). No `.env` file, no Google auth, no network, no per-token cost. Kokoro needs the system `espeak-ng` binary — run `brew install espeak-ng` first (one-time). Pass `--local-voice af_heart` (or any other Kokoro voice id) to switch voices.

## What it produces

- One `.wav` file per chapter, 24 kHz mono — lossless audio quality
- One `.mp3` file per chapter — compressed, roughly 10-15% of WAV size
- One combined `<book-name>.wav` with every chapter stitched together in order, produced automatically after all chapters are done
- One combined `<book-name>.mp3` with every chapter stitched together in order, produced automatically after all chapters are done (pass `--no-combine` to skip combination)
- A `_pcm_cache/` folder with raw audio bits (you can delete this once everything's done; it's just for the "resume where I left off" feature)

MP3 quality is controlled by the `--mp3-quality` flag (0.0 = highest quality ~73 kbps, default; 0.5 = balanced ~40 kbps, 0.8 = smallest ~33 kbps).

## Create audiobook with Storyteller (optional)

Once you have an EPUB file and its corresponding MP3 audiobook from this tool, you can combine them into a **synced-narration ("read-aloud") book** using [Storyteller](https://storyteller-platform.dev) — an open-source platform that aligns audio with ebook text so the words highlight as they are spoken. The resulting book can be read offline on iOS devices via the Storyteller mobile app.

### Self-host the Storyteller server

#### CPU-only (no GPU required)

```bash
# 1. Create a directory for Storyteller data
mkdir -p ~/Documents/Storyteller

# 2. Generate a secret key (one-time)
export STORYTELLER_SECRET_KEY=$(openssl rand -base64 32)
echo $STORYTELLER_SECRET_KEY > ./STORYTELLER_SECRET_KEY.txt
```

# 3. Start the server
```bash
docker run -d \
  --name storyteller \
  -v ~/Documents/Storyteller:/data:rw \
  -p 8001:8001 \
  -e STORYTELLER_SECRET_KEY=$STORYTELLER_SECRET_KEY \
  registry.gitlab.com/storyteller-platform/storyteller:latest
```

Or with Docker Compose — create `compose.yaml`:

```bash
touch compose.yaml 
vim compose.yaml
```
paste the following content:
```yaml
services:
  web:
    image: registry.gitlab.com/storyteller-platform/storyteller:latest
    volumes:
      - ~/Documents/Storyteller:/data:rw
    environment:
      - STORYTELLER_SECRET_KEY_FILE=/run/secrets/secret_key
    ports:
      - "8001:8001"
    secrets:
      - secret_key

secrets:
  secret_key:
    file: ./STORYTELLER_SECRET_KEY.txt
```

Put your generated key in `./STORYTELLER_SECRET_KEY.txt`, then run `docker compose up -d`.

#### With GPU acceleration (NVIDIA CUDA)

Storyteller supports GPU-accelerated audio transcription via CUDA. This significantly speeds up alignment.

Add GPU passthrough to the Docker Compose file:

```yaml
services:
  web:
    image: registry.gitlab.com/storyteller-platform/storyteller:latest
    volumes:
      - ~/Documents/Storyteller:/data:rw
    environment:
      - STORYTELLER_SECRET_KEY_FILE=/run/secrets/secret_key
    ports:
      - "8001:8001"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    secrets:
      - secret_key

secrets:
  secret_key:
    file: ./STORYTELLER_SECRET_KEY.txt
```

Requires the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) installed on the host.

#### Minimum resources

| Component | CPU-only | With CUDA |
|---|---|---|
| CPU | Up to 4 cores (Intel/AMD or ARM64 including Apple Silicon) | Same |
| GPU | Not required | NVIDIA (CUDA 11.8 / 12.x / 13.x) |
| RAM | 8 GB | 8 GB |
| Storage | 10 GB | 30 GB |
| Swap | ~12 GB recommended if RAM is tight | Same |

### Use it

1. Open `http://localhost:8001` in a browser and create your admin account.
2. Upload your **EPUB** file and the **MP3** audiobook produced by tts-novel.
3. Storyteller aligns the audio with the text automatically.
4. Install the [Storyteller iOS app](https://apps.apple.com/app/storyteller) and connect to your server to read and listen offline.

For the full self-hosting guide, see [https://storyteller-platform.dev/docs/installation/self-hosting](https://storyteller-platform.dev/docs/installation/self-hosting).

### remote host via tailscale

https://storyteller-platform.dev/docs/community-guides/tailscale

```bash
# on computer with tailscale installed
tailscale serve --https=443 --bg 8001
```