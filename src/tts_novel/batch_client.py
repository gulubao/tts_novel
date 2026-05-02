"""Gemini Developer API inline-batch client for TTS cache population."""

import time
from dataclasses import dataclass
from datetime import datetime

from google import genai
from google.genai import errors

from tts_novel.backends.base import BlockedContentError
from tts_novel.config import DEFAULT_TTS_MODEL, ClientSettings
from tts_novel.gemini_request import build_tts_inline_request
from tts_novel.google_auth import is_api_key_invalid_error

TERMINAL_BATCH_STATES = {
    "JOB_STATE_SUCCEEDED",
    "JOB_STATE_PARTIALLY_SUCCEEDED",
    "JOB_STATE_FAILED",
    "JOB_STATE_CANCELLED",
    "JOB_STATE_EXPIRED",
}

SUCCESSFUL_BATCH_STATES = {
    "JOB_STATE_SUCCEEDED",
    "JOB_STATE_PARTIALLY_SUCCEEDED",
}


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass(frozen=True)
class BatchTTSRequest:
    key: str
    text: str
    voice: str
    style_preamble: str

    @property
    def prompt(self) -> str:
        return self.style_preamble + self.text


@dataclass(frozen=True)
class BatchTTSResult:
    key: str
    pcm: bytes | None
    error: str | None = None


class APIKeyInvalidError(RuntimeError):
    """Raised when a Gemini API-key transport can no longer authenticate."""


class GeminiBatchClient:
    """Submit inline Gemini Batch API jobs and return one result per request.

    The installed ``google-genai`` SDK supports inline batch requests only on
    the Gemini Developer API surface. Vertex AI batch requires Cloud Storage
    input and output, which is a different transport architecture.
    """

    def __init__(self, settings: ClientSettings, model_id: str = DEFAULT_TTS_MODEL):
        if settings.use_vertex:
            raise ValueError(
                "batch synthesis currently requires Gemini Developer API credentials "
                "(GEMINI_API_KEY). Vertex AI batch requires GCS input/output and is not "
                "the inline chapter-batch path implemented here. Use --synthesis-mode "
                "realtime with Vertex AI credentials."
            )
        self._client = genai.Client(api_key=settings.api_key)
        self._model_id = model_id
        self.api_key_invalid = False

    def synthesize(
        self,
        requests: list[BatchTTSRequest],
        *,
        display_name: str,
        poll_interval_s: float,
    ) -> list[BatchTTSResult]:
        if not requests:
            return []
        if self.api_key_invalid:
            raise APIKeyInvalidError("Gemini API key is invalid.")
        inline_requests = [
            build_tts_inline_request(
                key=request.key,
                prompt=request.prompt,
                voice_name=request.voice,
            )
            for request in requests
        ]
        try:
            job = self._client.batches.create(
                model=self._model_id,
                src=inline_requests,
                config={"display_name": display_name},
            )
            job_name = job.name
            print(
                f"[{_ts()}] batch: submitted {job_name} ({len(requests)} request(s), {display_name})",
                flush=True,
            )
            job = self._client.batches.get(name=job_name)
            while job.state.name not in TERMINAL_BATCH_STATES:
                print(
                    f"[{_ts()}] batch: {job_name} state={job.state.name}; polling in {poll_interval_s:.1f}s",
                    flush=True,
                )
                time.sleep(poll_interval_s)
                job = self._client.batches.get(name=job_name)
        except errors.ClientError as exc:
            if is_api_key_invalid_error(exc):
                self.api_key_invalid = True
                raise APIKeyInvalidError("Gemini API key is invalid.") from exc
            raise

        if job.state.name not in SUCCESSFUL_BATCH_STATES:
            raise RuntimeError(f"batch job {job_name} ended as {job.state.name}: {job.error}")
        if job.dest is None or not job.dest.inlined_responses:
            raise RuntimeError(f"batch job {job_name} returned no inline responses")
        if len(job.dest.inlined_responses) != len(requests):
            raise RuntimeError(
                f"batch job {job_name} returned {len(job.dest.inlined_responses)} response(s) "
                f"for {len(requests)} request(s)"
            )

        results: list[BatchTTSResult] = []
        for request, inline_response in zip(requests, job.dest.inlined_responses, strict=True):
            response_key = request.key
            if inline_response.metadata and inline_response.metadata.get("key"):
                response_key = inline_response.metadata["key"]
            if inline_response.error is not None:
                results.append(
                    BatchTTSResult(
                        key=response_key,
                        pcm=None,
                        error=str(inline_response.error),
                    )
                )
                continue
            try:
                pcm = _extract_audio(inline_response.response)
            except BlockedContentError as exc:
                results.append(BatchTTSResult(key=response_key, pcm=None, error=str(exc)))
                continue
            results.append(BatchTTSResult(key=response_key, pcm=pcm))
        return results


def _extract_audio(response) -> bytes:
    if response is None or not response.candidates:
        raise BlockedContentError(
            "TTS batch returned no candidates; the request was blocked before generation."
        )
    candidate = response.candidates[0]
    if candidate.content is None or candidate.content.parts is None:
        raise BlockedContentError(
            f"TTS batch produced no audio parts (finish_reason={candidate.finish_reason}); "
            "narration of this chunk was blocked post-hoc."
        )
    return candidate.content.parts[0].inline_data.data
