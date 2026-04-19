"""Command-line entry point."""

import argparse
from pathlib import Path

from tts_novel.config import DEFAULT_STYLE_PREAMBLE, DEFAULT_VOICE
from tts_novel.pipeline import ConversionPlan, convert


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tts-novel",
        description=(
            "Convert an EPUB file to one narrated WAV per chapter. Default backend "
            "is 'auto' (Gemini TTS with local Kokoro-82M fallback on content-policy "
            "blocks); '--backend local' bypasses Gemini entirely."
        ),
    )
    parser.add_argument("--input", required=True, type=Path, help="Path to the EPUB file.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./output"),
        help="Directory for per-chapter WAV files (default: ./output).",
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
        default=2500,
        help="Soft upper bound on characters per TTS request.",
    )
    parser.add_argument(
        "--no-combine",
        action="store_true",
        help=(
            "Skip the final step that stitches every chapter WAV into a single "
            "<epub-stem>.wav file under --output-dir. Only relevant when synthesising "
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
    )

    result = convert(plan)

    print(f"Output dir : {result.output_dir}")
    print(f"Chapters   : {len(result.chapters)}")
    print(f"Total audio: {result.total_seconds:.2f} s "
          f"({result.total_seconds / 60:.2f} min; {result.total_pcm_bytes:,} PCM bytes)")
    for ch in result.chapters:
        marker = "skip" if ch.skipped_existing else "new "
        fresh = sum(1 for r in ch.chunks if not r.cached)
        cached = sum(1 for r in ch.chunks if r.cached)
        print(
            f"  [{ch.eligible_index:03d}] doc={ch.doc_index:03d} {marker} "
            f"{ch.seconds:>7.2f}s  chunks={len(ch.chunks)} "
            f"(synth={fresh}, cached={cached})  file={ch.output_wav.name}"
        )

    if result.combined_wav is not None:
        print(
            f"Combined   : {result.combined_wav.name} "
            f"({result.combined_pcm_bytes:,} PCM bytes, "
            f"{result.combined_pcm_bytes / (24000 * 2):.2f} s)"
        )

    if result.blocked_chunks:
        print(f"Blocked chunks (filled by fallback): {len(result.blocked_chunks)}")
        for b in result.blocked_chunks:
            print(
                f"  chapter {b.chapter_eligible_index:03d} doc={b.chapter_doc_index:03d} "
                f"chunk {b.chunk_index:03d} chars={b.chars} — {b.reason}"
            )


if __name__ == "__main__":
    main()
