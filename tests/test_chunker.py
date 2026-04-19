from tts_novel.text_chunker import chunk_text


def test_empty_text_returns_no_chunks():
    assert chunk_text("") == []


def test_single_short_paragraph_is_one_chunk():
    assert chunk_text("Hello world.", max_chars=100) == ["Hello world."]


def test_two_paragraphs_fit_in_one_chunk():
    text = "First.\n\nSecond."
    assert chunk_text(text, max_chars=100) == ["First.\n\nSecond."]


def test_paragraph_boundary_splits_when_exceeded():
    text = "AAAA.\n\nBBBB.\n\nCCCC."
    # With max_chars=12, only one 5-char paragraph fits per chunk
    out = chunk_text(text, max_chars=6)
    assert out == ["AAAA.", "BBBB.", "CCCC."]


def test_oversized_paragraph_falls_back_to_sentence_split():
    paragraph = "One sentence. Two sentences. Three sentences."
    out = chunk_text(paragraph, max_chars=20)
    # Each chunk is shorter than 20 chars
    for c in out:
        assert len(c) <= 20, c
    # Joining restores the original content (ignoring re-joined whitespace)
    assert "One sentence." in out[0]
    assert any("Three sentences." in c for c in out)


def test_oversized_paragraph_and_then_normal_paragraph():
    text = "Sentence one. Sentence two. Sentence three.\n\nShort."
    out = chunk_text(text, max_chars=20)
    # Short paragraph should still be present as its own chunk at the end.
    assert out[-1] == "Short."
