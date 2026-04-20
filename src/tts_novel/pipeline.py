"""Pipeline orchestrator: EPUB path to WAV + MP3 per chapter with PCM cache."""

import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from tts_novel.backends import BackendMode, TTSBackend, build_backend
from tts_novel.audio_writer import (
    combine_audio_files,
    concat_pcm,
    duration_seconds,
    write_mp3,
    write_wav,
)
from tts_novel.config import (
    CHANNELS,
    DEFAULT_STYLE_PREAMBLE,
    DEFAULT_VOICE,
    SAMPLE_RATE_HZ,
    SAMPLE_WIDTH_BYTES,
)
from tts_novel.cost import CostEstimate, estimate, estimate_from_text_only
from tts_novel.epub_reader import Chapter, read_epub
from tts_novel.text_chunker import chunk_text


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
    Gemini cost is accumulated per fresh Gemini chunk and displayed in the
    progress line; cached chunks and Kokoro fallbacks contribute ``$0`` to the
    running tally because no billable API call occurred.
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
    gemini_cost_usd: float = 0.0
    gemini_input_tokens: int = 0
    gemini_audio_tokens: int = 0
    gemini_chunks: int = 0

    def tick(
        self,
        *,
        n: int = 1,
        synth_seconds: float | None = None,
        chapter_done: bool = False,
        kind: str = "",
        cost: CostEstimate | None = None,
    ) -> None:
        self.chunks_done += n
        if kind == "cached":
            self.cached_hits += n
        elif kind == "chapter_skip":
            self.skipped_chapter_chunks += n
        if synth_seconds is not None and synth_seconds > 0:
            self.synth_time_total += synth_seconds
            self.synth_count += 1
        if cost is not None:
            self.gemini_cost_usd += cost.total_usd
            self.gemini_input_tokens += cost.input_tokens
            self.gemini_audio_tokens += cost.audio_tokens
            self.gemini_chunks += 1
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
        cost_str = (
            f" cost ~${self.gemini_cost_usd:.4f}"
            if self.gemini_cost_usd > 0
            else ""
        )
        print(
            f"[{_ts()}] progress: "
            f"chunks {self.chunks_done}/{self.total_chunks} ({pct:5.1f}%) "
            f"chapters {self.chapters_done}/{self.total_chapters} "
            f"avg-synth {avg_str} elapsed {_fmt_hms(elapsed)} ETA {eta}"
            f"{cost_str}"
            + (f" [{kind}]" if kind else ""),
            flush=True,
        )


@dataclass
class ConversionPlan:
    epub_path: Path
    output_dir: Path
    cache_dir: Path
    voice: str = DEFAULT_VOICE
    style_preamble: str = DEFAULT_STYLE_PREAMBLE
    chapter_index: int | None = None
    min_chapter_chars: int = 2000
    max_chars_per_chunk: int = 833
    combine: bool = True
    backend_mode: BackendMode = "auto"
    local_voice: str = "bf_emma"
    local_lang_code: str = "b"
    mp3_quality: float | None = 0.0


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
    backend: str = ""
    billed_input_chars: int = 0
    audio_seconds: float = 0.0
    cost_usd: float = 0.0


@dataclass
class ChapterResult:
    eligible_index: int
    doc_index: int
    title: str
    output_wav: Path
    output_mp3: Path
    pcm_bytes: int
    seconds: float
    chunks: list[ChunkRecord] = field(default_factory=list)
    skipped_existing: bool = False
    gemini_cost_usd: float = 0.0


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
    combined_mp3: Path | None = None
    combined_mp3_bytes: int = 0
    blocked_chunks: list[BlockedChunkRecord] = field(default_factory=list)
    gemini_cost_usd: float = 0.0
    gemini_input_tokens: int = 0
    gemini_audio_tokens: int = 0
    gemini_chunks: int = 0

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


def _chapter_mp3_path(output_dir: Path, eligible_index: int) -> Path:
    return output_dir / f"chapter_{eligible_index:03d}.mp3"


def _synthesize_chapter(
    chapter: Chapter,
    eligible_index: int,
    plan: ConversionPlan,
    backend: TTSBackend,
    blocked_sink: list["BlockedChunkRecord"],
    progress: ProgressTracker,
) -> ChapterResult:
    wav_path = _chapter_wav_path(plan.output_dir, eligible_index)
    mp3_path = _chapter_mp3_path(plan.output_dir, eligible_index)

    if wav_path.exists() and mp3_path.exists():
        wav_size = wav_path.stat().st_size
        pcm_bytes = max(wav_size - 44, 0)
        mp3_size = mp3_path.stat().st_size
        chapter_chunks = len(chunk_text(chapter.text, max_chars=plan.max_chars_per_chunk))
        print(
            f"[{_ts()}] chapter {eligible_index:03d} doc={chapter.index:03d} "
            f"SKIP (existing {wav_path.name} {mp3_path.name}, "
            f"{pcm_bytes:,} pcm bytes, {mp3_size:,} mp3 bytes)",
            flush=True,
        )
        progress.tick(n=chapter_chunks, chapter_done=True, kind="chapter_skip")
        return ChapterResult(
            eligible_index=eligible_index,
            doc_index=chapter.index,
            title=chapter.title,
            output_wav=wav_path,
            output_mp3=mp3_path,
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
        chunk_cost: CostEstimate | None = None
        rec_backend = ""
        rec_billed_chars = 0
        rec_audio_seconds = 0.0
        rec_cost_usd = 0.0
        if cached:
            pcm = cache_path.read_bytes()
            status = f"cached ({len(pcm):,} bytes)"
            progress_kind = "cached"
            synth_seconds: float | None = None
            rec_backend = "cached"
        else:
            result = backend.synthesize(chunk)
            pcm = result.pcm
            cache_path.write_bytes(pcm)
            synth_seconds = result.seconds
            progress_kind = result.backend
            chunk_audio_seconds = duration_seconds(len(pcm))
            rec_backend = result.backend
            rec_audio_seconds = chunk_audio_seconds
            if result.backend == "gemini":
                rec_billed_chars = len(plan.style_preamble) + len(chunk)
                chunk_cost = estimate(rec_billed_chars, chunk_audio_seconds)
                rec_cost_usd = chunk_cost.total_usd
                status = (
                    f"{result.backend:6s} ({len(pcm):,} bytes in {result.seconds:.1f}s, "
                    f"~{chunk_audio_seconds:.1f}s audio, "
                    f"~${chunk_cost.total_usd:.4f} "
                    f"[in {chunk_cost.input_tokens}t ${chunk_cost.input_usd:.5f} "
                    f"+ out {chunk_cost.audio_tokens}t ${chunk_cost.output_usd:.5f}])"
                )
            else:
                status = (
                    f"{result.backend:6s} ({len(pcm):,} bytes in {result.seconds:.1f}s, "
                    f"~{chunk_audio_seconds:.1f}s audio, local=$0.0000)"
                )
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
                backend=rec_backend,
                billed_input_chars=rec_billed_chars,
                audio_seconds=rec_audio_seconds,
                cost_usd=rec_cost_usd,
            )
        )
        progress.tick(synth_seconds=synth_seconds, kind=progress_kind, cost=chunk_cost)

    full_pcm = concat_pcm(pcm_parts)
    write_wav(wav_path, full_pcm)
    write_mp3(mp3_path, full_pcm, mp3_quality=plan.mp3_quality)

    mp3_bytes = mp3_path.stat().st_size
    chapter_cost_usd = sum(r.cost_usd for r in records)
    fresh_gemini = sum(1 for r in records if r.backend == "gemini")
    cost_tail = (
        f" gemini=${chapter_cost_usd:.4f} ({fresh_gemini} fresh chunk(s))"
        if chapter_cost_usd > 0
        else ""
    )
    print(
        f"[{_ts()}] chapter {eligible_index:03d} doc={chapter.index:03d} "
        f"DONE  ({len(full_pcm):,} pcm bytes, "
        f"{duration_seconds(len(full_pcm)):.1f}s audio) -> {wav_path.name}, {mp3_path.name} ({mp3_bytes:,} bytes)"
        f"{cost_tail}",
        flush=True,
    )

    return ChapterResult(
        eligible_index=eligible_index,
        doc_index=chapter.index,
        title=chapter.title,
        output_wav=wav_path,
        output_mp3=mp3_path,
        pcm_bytes=len(full_pcm),
        seconds=duration_seconds(len(full_pcm)),
        chunks=records,
        skipped_existing=False,
        gemini_cost_usd=chapter_cost_usd,
    )


def _combined_wav_path(plan: ConversionPlan) -> Path:
    return plan.output_dir / f"{plan.epub_path.stem}.wav"


def _combined_mp3_path(plan: ConversionPlan) -> Path:
    return plan.output_dir / f"{plan.epub_path.stem}.mp3"


def _combine_chapter_wavs(plan: ConversionPlan, result: ConversionResult) -> None:
    """Stitch every chapter WAV and MP3 into single book-level files.

    No-op when running in single-chapter mode, when combining is disabled,
    when any chapter file is missing, or when the combined file already exists.
    """
    if plan.chapter_index is not None or not plan.combine:
        return
    if not result.chapters:
        return

    wav_book_path = _combined_wav_path(plan)
    mp3_book_path = _combined_mp3_path(plan)

    missing_wav = [ch for ch in result.chapters if not ch.output_wav.exists()]
    missing_mp3 = [ch for ch in result.chapters if not ch.output_mp3.exists()]

    if missing_wav or missing_mp3:
        print(
            f"[{_ts()}] book   SKIP ({len(missing_wav)} WAV(s), {len(missing_mp3)} MP3(s) missing; "
            f"not combining partial output)",
            flush=True,
        )
        return

    wav_exists = wav_book_path.exists()
    mp3_exists = mp3_book_path.exists()

    if wav_exists and mp3_exists:
        wav_size = wav_book_path.stat().st_size
        mp3_size = mp3_book_path.stat().st_size
        wav_pcm_bytes = max(wav_size - 44, 0)
        print(
            f"[{_ts()}] book   SKIP (existing {wav_book_path.name}, {wav_pcm_bytes:,} pcm bytes; "
            f"{mp3_book_path.name}, {mp3_size:,} bytes)",
            flush=True,
        )
        result.combined_wav = wav_book_path
        result.combined_pcm_bytes = wav_pcm_bytes
        result.combined_mp3 = mp3_book_path
        result.combined_mp3_bytes = mp3_size
        return

    chapter_wav_paths = [ch.output_wav for ch in result.chapters]
    chapter_mp3_paths = [ch.output_mp3 for ch in result.chapters]

    if not wav_exists:
        print(
            f"[{_ts()}] book   COMBINE ({len(result.chapters)} chapter WAVs) -> {wav_book_path.name}",
            flush=True,
        )
        combine_audio_files(chapter_wav_paths, wav_book_path, format="wav")
        wav_pcm_bytes = wav_book_path.stat().st_size - 44
        result.combined_wav = wav_book_path
        result.combined_pcm_bytes = wav_pcm_bytes
        print(
            f"[{_ts()}] book   DONE  ({result.combined_pcm_bytes:,} pcm bytes, "
            f"{duration_seconds(result.combined_pcm_bytes):.1f}s audio) -> {wav_book_path.name}",
            flush=True,
        )

    if not mp3_exists:
        print(
            f"[{_ts()}] book   COMBINE ({len(result.chapters)} chapter MP3s) -> {mp3_book_path.name}",
            flush=True,
        )
        combine_audio_files(chapter_mp3_paths, mp3_book_path, format="mp3", mp3_quality=plan.mp3_quality)
        mp3_bytes = mp3_book_path.stat().st_size
        result.combined_mp3 = mp3_book_path
        result.combined_mp3_bytes = mp3_bytes
        print(
            f"[{_ts()}] book   DONE  ({mp3_bytes:,} mp3 bytes) -> {mp3_book_path.name}",
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
    total_text_chars = 0
    for _, chapter in iter_set:
        chunk_list = chunk_text(chapter.text, max_chars=plan.max_chars_per_chunk)
        total_chunks += len(chunk_list)
        total_text_chars += sum(len(c) for c in chunk_list)
    progress = ProgressTracker(total_chunks=total_chunks, total_chapters=len(iter_set))
    print(
        f"[{_ts()}] plan: backend={plan.backend_mode} "
        f"{len(iter_set)} chapter(s), {total_chunks} chunk(s) total",
        flush=True,
    )
    if plan.backend_mode == "auto":
        preamble_chars = len(plan.style_preamble) * total_chunks
        upper_bound_chars = total_text_chars + preamble_chars
        planning_cost = estimate_from_text_only(upper_bound_chars)
        print(
            f"[{_ts()}] plan: Gemini cost estimate if all chunks synthesized fresh: "
            f"~${planning_cost.total_usd:.2f} "
            f"(input {planning_cost.input_tokens:,}t ~${planning_cost.input_usd:.4f} "
            f"+ output ~{planning_cost.audio_tokens:,}t ~${planning_cost.output_usd:.2f}; "
            f"assumes ~15 chars/s narration, actual billed usage may differ)",
            flush=True,
        )

    for eligible_idx, chapter in iter_set:
        result.chapters.append(
            _synthesize_chapter(
                chapter, eligible_idx, plan, backend,
                result.blocked_chunks, progress,
            )
        )

    result.gemini_cost_usd = progress.gemini_cost_usd
    result.gemini_input_tokens = progress.gemini_input_tokens
    result.gemini_audio_tokens = progress.gemini_audio_tokens
    result.gemini_chunks = progress.gemini_chunks

    _combine_chapter_wavs(plan, result)
    return result


def format_wav_metadata() -> dict:
    return {
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "channels": CHANNELS,
        "sample_width_bytes": SAMPLE_WIDTH_BYTES,
    }
