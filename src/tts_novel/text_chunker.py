"""Paragraph-aware chunker with sentence-level and word-level fallback."""

import re

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def _split_long_span(text: str, max_chars: int) -> list[str]:
    words = text.split()
    if not words:
        return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]

    out: list[str] = []
    buf: list[str] = []
    buf_len = 0
    for word in words:
        if len(word) > max_chars:
            if buf:
                out.append(" ".join(buf))
                buf, buf_len = [], 0
            out.extend(word[i : i + max_chars] for i in range(0, len(word), max_chars))
            continue
        added_len = len(word) + (1 if buf else 0)
        if buf and buf_len + added_len > max_chars:
            out.append(" ".join(buf))
            buf, buf_len = [word], len(word)
            continue
        buf.append(word)
        buf_len += added_len
    if buf:
        out.append(" ".join(buf))
    return out


def _split_long_paragraph(paragraph: str, max_chars: int) -> list[str]:
    sentences = _SENTENCE_BOUNDARY.split(paragraph)
    out: list[str] = []
    buf: list[str] = []
    buf_len = 0
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) > max_chars:
            if buf:
                out.append(" ".join(buf))
                buf, buf_len = [], 0
            out.extend(_split_long_span(sentence, max_chars))
            continue
        added_len = len(sentence) + (1 if buf else 0)
        if buf and buf_len + added_len > max_chars:
            out.append(" ".join(buf))
            buf, buf_len = [], 0
        buf.append(sentence)
        buf_len += added_len
    if buf:
        out.append(" ".join(buf))
    return out


def chunk_text(text: str, max_chars: int = 400) -> list[str]:
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0

    for paragraph in paragraphs:
        para_with_sep = len(paragraph) + (2 if buf else 0)

        if len(paragraph) > max_chars:
            if buf:
                chunks.append("\n\n".join(buf))
                buf, buf_len = [], 0
            chunks.extend(_split_long_paragraph(paragraph, max_chars))
            continue

        if buf and buf_len + para_with_sep > max_chars:
            chunks.append("\n\n".join(buf))
            buf, buf_len = [], 0
            para_with_sep = len(paragraph)

        buf.append(paragraph)
        buf_len += para_with_sep

    if buf:
        chunks.append("\n\n".join(buf))
    return chunks
