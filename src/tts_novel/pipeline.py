"""Pipeline orchestrator: EPUB path to one WAV per chapter with PCM cache."""

import time
import wave
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _fmt_hms(seconds: float) -> str:
    s = max(int(seconds), 0)
    return f"{s // 3600}h{(s % 3600) // 60:02d}m{s % 60:02d}s"


@dataclass
class ProgressTracker:
    """Rolling progress meter printed after every chunk-level event.

    Tracks total chunks planned across the whole run, how many are done, and
    a rolling mean of synthesis wall-time for ETA. Cache hits and chapter-level
    skips bump the counter without contributing to the synth-time mean.
    """

    total_chunks: int
    total_chapters: int
    start_time: float = field(default_factory=time.monotonic)
    chunks_done: int = 0
    chapters_done: int = 0
    synth_time_total: float = 0.0
    synth_count: int = 0
    cached_hits: int = 0
    skipped_chapter_chunks: int = 0

    def tick(
        self,
        *,
        n: int = 1,
        synth_seconds: float | None = None,
        chapter_done: bool = False,
        kind: str = "",
    ) -> None:
        self.chunks_done += n
        if kind == "cached":
            self.cached_hits += n
        elif kind == "chapter_skip":
            self.skipped_chapter_chunks += n
        if synth_seconds is not None and synth_seconds > 0:
            self.synth_time_total += synth_seconds
            self.synth_count += 1
        if chapter_done:
            self.chapters_done += 1
        self._print(kind)

    def _print(self, kind: str) -> None:
        pct = 100.0 * self.chunks_done / max(self.total_chunks, 1)
        remaining_chunks = self.total_chunks - self.chunks_done
        elapsed = time.monotonic() - self.start_time
        if self.synth_count > 0:
            avg = self.synth_time_total / self.synth_count
            eta = _fmt_hms(avg * remaining_chunks)
            avg_str = f"{avg:.1f}s"
        else:
            eta = "?"
            avg_str = "n/a"
        print(
            f"[{_ts()}] progress: "
            f"chunks {self.chunks_done}/{self.total_chunks} ({pct:5.1f}%) "
            f"chapters {self.chapters_done}/{self.total_chapters} "
            f"avg-synth {avg_str} elapsed {_fmt_hms(elapsed)} ETA {eta}"
            + (f" [{kind}]" if kind else ""),
            flush=True,
        )


from tts_novel.backends import BackendMode, TTSBackend, build_backend
from tts_novel.config import (
    CHANNELS,
    DEFAULT_STYLE_PREAMBLE,
    DEFAULT_VOICE,
    SAMPLE_RATE_HZ,
    SAMPLE_WIDTH_BYTES,
)
from tts_novel.epub_reader import Chapter, read_epub
from tts_novel.text_chunker import chunk_text
from tts_novel.wav_writer import concat_pcm, duration_seconds, write_wav


@dataclass
class ConversionPlan:
    epub_path: Path
    output_dir: Path
    cache_dir: Path
    voice: str = DEFAULT_VOICE
    style_preamble: str = DEFAULT_STYLE_PREAMBLE
    chapter_index: int | None = None
    min_chapter_chars: int = 2000
    max_chars_per_chunk: int = 2500
    combine: bool = True
    backend_mode: BackendMode = "auto"
    local_voice: str = "bf_emma"
    local_lang_code: str = "b"


@dataclass
class ChunkRecord:
    chapter_doc_index: int
    chapter_eligible_index: int
    chapter_title: str
    chunk_index: int
    chars: int
    pcm_bytes: int
    cached: bool
    cache_path: Path


@dataclass
class ChapterResult:
    eligible_index: int
    doc_index: int
    title: str
    output_wav: Path
    pcm_bytes: int
    seconds: float
    chunks: list[ChunkRecord] = field(default_factory=list)
    skipped_existing: bool = False


@dataclass
class BlockedChunkRecord:
    chapter_doc_index: int
    chapter_eligible_index: int
    chunk_index: int
    chars: int
    reason: str


@dataclass
class ConversionResult:
    output_dir: Path
    chapters: list[ChapterResult] = field(default_factory=list)
    combined_wav: Path | None = None
    combined_pcm_bytes: int = 0
    blocked_chunks: list[BlockedChunkRecord] = field(default_factory=list)

    @property
    def total_pcm_bytes(self) -> int:
        return sum(c.pcm_bytes for c in self.chapters)

    @property
    def total_seconds(self) -> float:
        return sum(c.seconds for c in self.chapters)


def select_chapters(
    chapters: list[Chapter],
    *,
    min_chars: int,
    only_eligible_index: int | None = None,
) -> list[Chapter]:
    eligible = [c for c in chapters if len(c.text) >= min_chars]
    if only_eligible_index is None:
        return eligible
    if only_eligible_index < 0 or only_eligible_index >= len(eligible):
        raise IndexError(
            f"--chapter {only_eligible_index} out of range; "
            f"there are {len(eligible)} eligible chapters (indices 0..{len(eligible) - 1})."
        )
    return [eligible[only_eligible_index]]


def _chapter_wav_path(output_dir: Path, eligible_index: int) -> Path:
    return output_dir / f"chapter_{eligible_index:03d}.wav"


def _synthesize_chapter(
    chapter: Chapter,
    eligible_index: int,
    plan: ConversionPlan,
    backend: TTSBackend,
    blocked_sink: list["BlockedChunkRecord"],
    progress: ProgressTracker,
) -> ChapterResult:
    wav_path = _chapter_wav_path(plan.output_dir, eligible_index)

    if wav_path.exists():
        size = wav_path.stat().st_size
        pcm_bytes = max(size - 44, 0)  # subtract WAV header
        chapter_chunks = len(chunk_text(chapter.text, max_chars=plan.max_chars_per_chunk))
        print(
            f"[{_ts()}] chapter {eligible_index:03d} doc={chapter.index:03d} "
            f"SKIP (existing {wav_path.name}, {pcm_bytes:,} pcm bytes)",
            flush=True,
        )
        progress.tick(n=chapter_chunks, chapter_done=True, kind="chapter_skip")
        return ChapterResult(
            eligible_index=eligible_index,
            doc_index=chapter.index,
            title=chapter.title,
            output_wav=wav_path,
            pcm_bytes=pcm_bytes,
            seconds=duration_seconds(pcm_bytes),
            chunks=[],
            skipped_existing=True,
        )

    chunks = chunk_text(chapter.text, max_chars=plan.max_chars_per_chunk)
    pcm_parts: list[bytes] = []
    records: list[ChunkRecord] = []

    print(
        f"[{_ts()}] chapter {eligible_index:03d} doc={chapter.index:03d} "
        f"START ({len(chunks)} chunks, {len(chapter.text):,} chars)",
        flush=True,
    )

    for ci, chunk in enumerate(chunks):
        cache_path = plan.cache_dir / f"ch{chapter.index:03d}_c{ci:03d}.pcm"
        cached = cache_path.exists()
        if cached:
            pcm = cache_path.read_bytes()
            status = f"cached ({len(pcm):,} bytes)"
            progress_kind = "cached"
            synth_seconds: float | None = None
        else:
            result = backend.synthesize(chunk)
            pcm = result.pcm
            cache_path.write_bytes(pcm)
            synth_seconds = result.seconds
            progress_kind = result.backend
            status = f"{result.backend:6s} ({len(pcm):,} bytes in {result.seconds:.1f}s)"
            if result.fallback_reason is not None:
                status += f" — primary blocked: {result.fallback_reason}"
                blocked_sink.append(
                    BlockedChunkRecord(
                        chapter_doc_index=chapter.index,
                        chapter_eligible_index=eligible_index,
                        chunk_index=ci,
                        chars=len(chunk),
                        reason=f"primary blocked, {result.backend} filled: {result.fallback_reason}",
                    )
                )
        print(
            f"[{_ts()}]   [chapter {eligible_index:03d} doc={chapter.index:03d}] "
            f"chunk {ci + 1}/{len(chunks)} chars={len(chunk)} {status}",
            flush=True,
        )
        pcm_parts.append(pcm)
        records.append(
            ChunkRecord(
                chapter_doc_index=chapter.index,
                chapter_eligible_index=eligible_index,
                chapter_title=chapter.title,
                chunk_index=ci,
                chars=len(chunk),
                pcm_bytes=len(pcm),
                cached=cached,
                cache_path=cache_path,
            )
        )
        progress.tick(synth_seconds=synth_seconds, kind=progress_kind)

    full_pcm = concat_pcm(pcm_parts)
    write_wav(wav_path, full_pcm)

    print(
        f"[{_ts()}] chapter {eligible_index:03d} doc={chapter.index:03d} "
        f"DONE  ({len(full_pcm):,} pcm bytes, "
        f"{duration_seconds(len(full_pcm)):.1f}s audio) -> {wav_path.name}",
        flush=True,
    )

    return ChapterResult(
        eligible_index=eligible_index,
        doc_index=chapter.index,
        title=chapter.title,
        output_wav=wav_path,
        pcm_bytes=len(full_pcm),
        seconds=duration_seconds(len(full_pcm)),
        chunks=records,
        skipped_existing=False,
    )


def _combined_wav_path(plan: ConversionPlan) -> Path:
    return plan.output_dir / f"{plan.epub_path.stem}.wav"


def _combine_chapter_wavs(plan: ConversionPlan, result: ConversionResult) -> None:
    """Stitch every chapter WAV into a single book-level WAV.

    No-op when running in single-chapter mode, when combining is disabled,
    when any chapter WAV is missing, or when the combined file already exists.
    """
    if plan.chapter_index is not None or not plan.combine:
        return
    if not result.chapters:
        return

    book_path = _combined_wav_path(plan)
    missing = [ch for ch in result.chapters if not ch.output_wav.exists()]
    if missing:
        print(
            f"[{_ts()}] book   SKIP ({len(missing)} chapter WAV(s) missing; "
            f"not combining partial output)",
            flush=True,
        )
        return

    if book_path.exists():
        size = book_path.stat().st_size
        pcm_bytes = max(size - 44, 0)
        print(
            f"[{_ts()}] book   SKIP (existing {book_path.name}, {pcm_bytes:,} pcm bytes)",
            flush=True,
        )
        result.combined_wav = book_path
        result.combined_pcm_bytes = pcm_bytes
        return

    print(
        f"[{_ts()}] book   COMBINE ({len(result.chapters)} chapter WAVs) -> {book_path.name}",
        flush=True,
    )

    total_frames = 0
    book_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(book_path), "wb") as out:
        out.setnchannels(CHANNELS)
        out.setsampwidth(SAMPLE_WIDTH_BYTES)
        out.setframerate(SAMPLE_RATE_HZ)
        for ch in result.chapters:
            with wave.open(str(ch.output_wav), "rb") as wf:
                if (
                    wf.getnchannels() != CHANNELS
                    or wf.getsampwidth() != SAMPLE_WIDTH_BYTES
                    or wf.getframerate() != SAMPLE_RATE_HZ
                ):
                    raise RuntimeError(
                        f"Chapter WAV {ch.output_wav} has incompatible format; "
                        f"expected {CHANNELS}ch/{SAMPLE_WIDTH_BYTES}B/{SAMPLE_RATE_HZ}Hz"
                    )
                out.writeframes(wf.readframes(wf.getnframes()))
                total_frames += wf.getnframes()

    total_pcm_bytes = total_frames * CHANNELS * SAMPLE_WIDTH_BYTES
    result.combined_wav = book_path
    result.combined_pcm_bytes = total_pcm_bytes
    print(
        f"[{_ts()}] book   DONE  ({total_pcm_bytes:,} pcm bytes, "
        f"{duration_seconds(total_pcm_bytes):.1f}s audio) -> {book_path.name}",
        flush=True,
    )


def convert(plan: ConversionPlan, backend: TTSBackend | None = None) -> ConversionResult:
    if backend is None:
        backend = build_backend(
            plan.backend_mode,
            voice=plan.voice,
            style_preamble=plan.style_preamble,
            local_voice=plan.local_voice,
            local_lang_code=plan.local_lang_code,
        )

    plan.output_dir.mkdir(parents=True, exist_ok=True)
    plan.cache_dir.mkdir(parents=True, exist_ok=True)

    all_chapters = read_epub(plan.epub_path)
    eligible = select_chapters(all_chapters, min_chars=plan.min_chapter_chars)

    if plan.chapter_index is None:
        iter_set: list[tuple[int, Chapter]] = list(enumerate(eligible))
    else:
        picked = select_chapters(
            all_chapters,
            min_chars=plan.min_chapter_chars,
            only_eligible_index=plan.chapter_index,
        )[0]
        iter_set = [(plan.chapter_index, picked)]

    result = ConversionResult(output_dir=plan.output_dir)

    total_chunks = 0
    for _, chapter in iter_set:
        total_chunks += len(chunk_text(chapter.text, max_chars=plan.max_chars_per_chunk))
    progress = ProgressTracker(total_chunks=total_chunks, total_chapters=len(iter_set))
    print(
        f"[{_ts()}] plan: backend={plan.backend_mode} "
        f"{len(iter_set)} chapter(s), {total_chunks} chunk(s) total",
        flush=True,
    )

    for eligible_idx, chapter in iter_set:
        result.chapters.append(
            _synthesize_chapter(
                chapter, eligible_idx, plan, backend,
                result.blocked_chunks, progress,
            )
        )

    _combine_chapter_wavs(plan, result)
    return result


def format_wav_metadata() -> dict:
    return {
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "channels": CHANNELS,
        "sample_width_bytes": SAMPLE_WIDTH_BYTES,
    }
