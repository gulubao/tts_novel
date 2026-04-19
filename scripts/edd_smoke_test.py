"""Evidence-based smoke test for the EPUB->TTS pipeline.

Runs every logical stage on real data and prints a human-readable report.
"""

import argparse
import json
import wave
from pathlib import Path

from tts_novel.config import (
    CHANNELS,
    DEFAULT_STYLE_PREAMBLE,
    DEFAULT_VOICE,
    SAMPLE_RATE_HZ,
    SAMPLE_WIDTH_BYTES,
    load_client_settings,
)
from tts_novel.epub_reader import read_epub
from tts_novel.pipeline import select_chapters
from tts_novel.text_chunker import chunk_text
from tts_novel.tts_client import TTSClient
from tts_novel.wav_writer import duration_seconds, write_wav

SECTION = "=" * 72
SUB = "-" * 72


def section(title: str) -> None:
    print(f"\n{SECTION}\n{title}\n{SECTION}")


def head(text: str, n: int = 500) -> str:
    if len(text) <= n:
        return text
    return text[:n] + f"\n... [+{len(text) - n} more chars]"


def run(epub_path: Path, out_wav: Path, voice: str) -> None:
    section("1. EPUB ingestion")
    chapters = read_epub(epub_path)
    print(f"epub: {epub_path}")
    print(f"non-empty document items: {len(chapters)}")
    for c in chapters[:8]:
        print(f"  [{c.index:03d}] title={c.title!r:35s} chars={len(c.text):>6d}")
    if len(chapters) > 8:
        print(f"  ... (+{len(chapters) - 8} more)")

    section("2. Chapter selection")
    selected = select_chapters(chapters, first_n=1, min_chars=2000)
    if not selected:
        raise RuntimeError("No eligible chapter found; min_chars filter too strict.")
    chap = selected[0]
    print(f"selected chapter: index={chap.index} title={chap.title!r} chars={len(chap.text)}")
    print(f"{SUB}\nfirst 500 chars of chapter text:\n{SUB}")
    print(head(chap.text, 500))

    section("3. Chunking")
    chunks = chunk_text(chap.text, max_chars=2500)
    print(f"chunks produced: {len(chunks)}")
    for i, ch in enumerate(chunks):
        print(f"  chunk[{i:02d}] chars={len(ch):>5d}  preview={ch[:80].replace(chr(10), ' ')!r}")

    section("4. TTS round-trip on a single small chunk")
    probe_text = chunks[0]
    if len(probe_text) > 600:
        first_paras = probe_text.split("\n\n")[:2]
        probe_text = "\n\n".join(first_paras)[:600]
    print(f"probe prompt chars (after trim for smoke test): {len(probe_text)}")
    print(f"{SUB}\nprobe text:\n{SUB}")
    print(probe_text)

    client = TTSClient(load_client_settings())
    pcm = client.synthesize(probe_text, voice_name=voice, style_preamble=DEFAULT_STYLE_PREAMBLE)

    section("5. Audio verification")
    print(f"raw PCM bytes returned: {len(pcm)}")
    print(f"first 32 bytes (hex)  : {pcm[:32].hex(' ')}")
    write_wav(out_wav, pcm)
    with wave.open(str(out_wav), "rb") as wf:
        meta = {
            "path": str(out_wav),
            "nchannels": wf.getnchannels(),
            "sampwidth_bytes": wf.getsampwidth(),
            "framerate_hz": wf.getframerate(),
            "nframes": wf.getnframes(),
        }
    expected = {
        "nchannels": CHANNELS,
        "sampwidth_bytes": SAMPLE_WIDTH_BYTES,
        "framerate_hz": SAMPLE_RATE_HZ,
    }
    print("WAV header (read back from disk):")
    print(json.dumps(meta, indent=2))
    print(f"expected format: {expected}")
    ok = all(meta[k] == v for k, v in expected.items())
    print(f"format match   : {ok}")
    print(f"duration_seconds (from PCM): {duration_seconds(len(pcm)):.3f}")
    print(f"duration_seconds (from header): {meta['nframes'] / meta['framerate_hz']:.3f}")

    section("6. Summary")
    print(
        json.dumps(
            {
                "epub": str(epub_path),
                "chapters_seen": len(chapters),
                "chapter_selected_index": chap.index,
                "chapter_selected_chars": len(chap.text),
                "chunker_output_chunks": len(chunks),
                "probe_prompt_chars": len(probe_text),
                "pcm_bytes": len(pcm),
                "wav_path": str(out_wav),
                "format_match": ok,
            },
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="EDD smoke test for EPUB->TTS pipeline.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path("./output/_smoke_probe.wav"))
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    args = parser.parse_args()
    run(args.input, args.output, args.voice)


if __name__ == "__main__":
    main()
