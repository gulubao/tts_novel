"""Command-line entry point."""

import argparse
from pathlib import Path

from tts_novel.config import (
    DEFAULT_STYLE_PREAMBLE,
    DEFAULT_TTS_MODEL,
    DEFAULT_VOICE,
    TTS_MODELS,
)
from tts_novel.pipeline import BATCH_PRICE_MULTIPLIER, ChapterResult, ConversionPlan, convert


def _chapter_synthesis_summary(chapter: ChapterResult) -> str:
    gemini = sum(
        1
        for record in chapter.chunks
        if not record.cached and record.backend in {"gemini", "gemini_batch"}
    )
    local = sum(
        1
        for record in chapter.chunks
        if not record.cached and record.backend not in {"", "cached", "gemini", "gemini_batch"}
    )
    cached = sum(1 for record in chapter.chunks if record.cached)
    parts = [f"gemini={gemini}"]
    if local:
        parts.append(f"local={local}")
    parts.append(f"cached={cached}")
    return ", ".join(parts)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tts-novel",
        description=(
            "Convert an EPUB file to one narrated WAV and MP3 per chapter. Default "
            "synthesis is Gemini Batch API one chapter at a time, with local "
            "Kokoro-82M fallback on content-policy blocks. '--backend local' "
            "bypasses Gemini entirely."
        ),
    )
    parser.add_argument("--input", required=True, type=Path, help="Path to the EPUB file.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./output"),
        help="Directory for per-chapter WAV and MP3 files (default: ./output).",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="Directory for per-chunk PCM cache (default: <output-dir>/_pcm_cache).",
    )
    parser.add_argument(
        "--backend",
        choices=("auto", "local"),
        default="auto",
        help=(
            "Which synthesis backend to use. 'auto' (default): call Gemini TTS "
            "first, fall back to local Kokoro-82M on a content-policy block. "
            "'local': use Kokoro-82M only, no Google API calls or authentication."
        ),
    )
    parser.add_argument(
        "--synthesis-mode",
        choices=("batch", "realtime"),
        default="batch",
        help=(
            "Gemini synthesis transport. 'batch' (default): submit cache-missing "
            "chunks one chapter at a time through Gemini Batch API at batch "
            "pricing. 'realtime': send one synchronous request per missing chunk. "
            "--backend local always runs locally regardless of this setting."
        ),
    )
    parser.add_argument(
        "--batch-poll-interval-s",
        type=float,
        default=30.0,
        help="Seconds between Gemini Batch API status polls (default: 30).",
    )
    parser.add_argument(
        "--batch-max-input-mib",
        type=float,
        default=18.0,
        help=(
            "Soft maximum estimated input size per inline batch job in MiB "
            "(default: 18, below Gemini's 20 MiB inline request guidance)."
        ),
    )
    parser.add_argument(
        "--batch-max-estimated-output-mib",
        type=float,
        default=96.0,
        help=(
            "Soft maximum estimated base64 audio output per inline batch job in MiB "
            "(default: 96). Chapters above this estimate are split into multiple "
            "batch jobs."
        ),
    )
    parser.add_argument("--voice", default=DEFAULT_VOICE, help="Gemini prebuilt voice name.")
    parser.add_argument(
        "--style-preamble",
        default=DEFAULT_STYLE_PREAMBLE,
        help="Style instruction prepended to every Gemini synthesis prompt.",
    )
    parser.add_argument(
        "--chapter",
        type=int,
        default=None,
        help=(
            "Synthesize only the chapter at this 0-based eligible index. "
            "Omit to synthesize every eligible chapter in order."
        ),
    )
    parser.add_argument(
        "--min-chapter-chars",
        type=int,
        default=2000,
        help="Minimum text length for a document to count as a chapter.",
    )
    parser.add_argument(
        "--max-chars-per-chunk",
        type=int,
        default=200,
        help="Maximum characters per TTS request (default 200, per Deepgram TTS chunking guidance for long-form content).",
    )
    parser.add_argument(
        "--no-combine",
        action="store_true",
        help=(
            "Skip the final step that stitches every chapter WAV and MP3 into single "
            "<epub-stem>.wav and <epub-stem>.mp3 files under --output-dir. Only relevant when synthesising "
            "all chapters (ignored with --chapter N)."
        ),
    )
    parser.add_argument(
        "--local-voice",
        default="bf_emma",
        help="Kokoro voice id (default: bf_emma — British female).",
    )
    parser.add_argument(
        "--local-lang-code",
        default="b",
        help="Kokoro language code (default: b — British English).",
    )
    parser.add_argument(
        "--mp3-quality",
        type=float,
        default=0.0,
        help=(
            "MP3 compression level in [0.0, 0.9]. 0.0 = highest quality (~73 kbps VBR, default), "
            "0.5 = balanced (~40 kbps), 0.8 = smallest (~33 kbps)."
        ),
    )
    parser.add_argument(
        "--tts-model",
        default=DEFAULT_TTS_MODEL,
        choices=sorted(TTS_MODELS),
        help=(
            f"Gemini TTS model ID (default: {DEFAULT_TTS_MODEL}). "
            "3.1 Flash TTS yields higher quality at 2x cost; 2.5 Flash TTS is the cost-effective default."
        ),
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    cache_dir = args.cache_dir if args.cache_dir is not None else args.output_dir / "_pcm_cache"

    plan = ConversionPlan(
        epub_path=args.input,
        output_dir=args.output_dir,
        cache_dir=cache_dir,
        voice=args.voice,
        style_preamble=args.style_preamble,
        chapter_index=args.chapter,
        min_chapter_chars=args.min_chapter_chars,
        max_chars_per_chunk=args.max_chars_per_chunk,
        combine=not args.no_combine,
        backend_mode=args.backend,
        local_voice=args.local_voice,
        local_lang_code=args.local_lang_code,
        mp3_quality=args.mp3_quality,
        tts_model=args.tts_model,
        synthesis_mode=args.synthesis_mode,
        batch_poll_interval_s=args.batch_poll_interval_s,
        batch_max_input_mib=args.batch_max_input_mib,
        batch_max_estimated_output_mib=args.batch_max_estimated_output_mib,
    )

    result = convert(plan)

    print(f"Output dir : {result.output_dir}")
    print(f"Chapters   : {len(result.chapters)}")
    print(f"Total audio: {result.total_seconds:.2f} s "
          f"({result.total_seconds / 60:.2f} min; {result.total_pcm_bytes:,} PCM bytes)")
    for ch in result.chapters:
        marker = "skip" if ch.skipped_existing else "new "
        mp3_bytes = ch.output_mp3.stat().st_size if ch.output_mp3.exists() else 0
        cost_tail = f"  gemini=${ch.gemini_cost_usd:.4f}" if ch.gemini_cost_usd > 0 else ""
        print(
            f"  [{ch.eligible_index:03d}] doc={ch.doc_index:03d} {marker} "
            f"{ch.seconds:>7.2f}s  chunks={len(ch.chunks)} "
            f"({_chapter_synthesis_summary(ch)})  {ch.output_wav.name} + "
            f"{ch.output_mp3.name} ({mp3_bytes:,} bytes)"
            f"{cost_tail}"
        )

    if result.combined_wav is not None:
        print(
            f"Combined WAV: {result.combined_wav.name} "
            f"({result.combined_pcm_bytes:,} PCM bytes, "
            f"{result.combined_pcm_bytes / (24000 * 2):.2f} s)"
        )
    if result.combined_mp3 is not None:
        print(
            f"Combined MP3: {result.combined_mp3.name} "
            f"({result.combined_mp3_bytes:,} bytes)"
        )

    if result.gemini_chunks > 0:
        model_rates = TTS_MODELS[args.tts_model]
        price_multiplier = (
            BATCH_PRICE_MULTIPLIER
            if args.backend == "auto" and args.synthesis_mode == "batch"
            else 1.0
        )
        input_rate = model_rates["input_usd_per_1m"] * price_multiplier
        output_rate = model_rates["audio_usd_per_1m"] * price_multiplier
        input_usd = result.gemini_input_tokens * input_rate / 1_000_000
        output_usd = result.gemini_audio_tokens * output_rate / 1_000_000
        surface = "Gemini Batch API" if price_multiplier == BATCH_PRICE_MULTIPLIER else "Gemini API"
        print(
            f"{surface} cost (this run, {result.gemini_chunks} Gemini-billed chunk(s)): "
            f"~${result.gemini_cost_usd:.4f}  "
            f"[input {result.gemini_input_tokens:,}t ${input_usd:.4f} + "
            f"output {result.gemini_audio_tokens:,}t ${output_usd:.4f}]"
        )
        print(
            f"  Model: {args.tts_model}  Rates: "
            f"text ${input_rate:.2f} / 1M tokens, "
            f"audio ${output_rate:.2f} / 1M tokens "
            "(4 chars ≈ 1 token, 25 audio tokens per second of audio). "
            "Estimate only; reconcile against the Cloud Billing invoice."
        )
    else:
        print("Gemini API cost (this run): $0.0000 (all chunks cached or local backend).")

    if result.blocked_chunks:
        print(f"Gemini-failed chunks filled by local fallback: {len(result.blocked_chunks)}")
        for b in result.blocked_chunks:
            print(
                f"  chapter {b.chapter_eligible_index:03d} doc={b.chapter_doc_index:03d} "
                f"chunk {b.chunk_index:03d} chars={b.chars} — {b.reason}"
            )


if __name__ == "__main__":
    main()
