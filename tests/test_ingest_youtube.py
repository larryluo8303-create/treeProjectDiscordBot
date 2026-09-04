"""Tests for ingestion.ingest_youtube module — URL parsing, segment merging, document conversion."""

from ingestion.ingest_youtube import (
    _extract_video_id,
    _merge_transcript_segments,
    _venv_bin_candidates,
    extract_video_id,
    transcript_to_documents,
)


class TestExtractVideoId:
    def test_public_alias(self):
        assert extract_video_id is _extract_video_id
        assert extract_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_standard_url(self):
        assert _extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_short_url(self):
        assert _extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_embed_url(self):
        assert _extract_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_shorts_url(self):
        assert _extract_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_raw_video_id(self):
        assert _extract_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_url_with_params(self):
        assert _extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=120") == "dQw4w9WgXcQ"

    def test_invalid_url(self):
        assert _extract_video_id("https://www.google.com") is None

    def test_empty_string(self):
        assert _extract_video_id("") is None

    def test_too_short_id(self):
        assert _extract_video_id("abc") is None


class TestVenvBinCandidates:
    def test_includes_plain_name(self):
        paths = _venv_bin_candidates("ffmpeg")
        assert any(p.endswith("ffmpeg") or p.endswith("ffmpeg.exe") for p in paths)


class TestMergeTranscriptSegments:
    def test_continuous_segments(self):
        segments = [
            {"start": 0.0, "duration": 2.0, "text": "Hello"},
            {"start": 2.0, "duration": 2.0, "text": "world"},
            {"start": 4.0, "duration": 2.0, "text": "today"},
        ]
        result = _merge_transcript_segments(segments, gap_seconds=3.0)
        assert len(result) == 1
        assert "Hello" in result[0]
        assert "world" in result[0]
        assert "today" in result[0]

    def test_gap_splits_paragraphs(self):
        segments = [
            {"start": 0.0, "duration": 2.0, "text": "First sentence"},
            {"start": 10.0, "duration": 2.0, "text": "Second sentence"},
        ]
        result = _merge_transcript_segments(segments, gap_seconds=3.0)
        assert len(result) == 2
        assert result[0] == "First sentence"
        assert result[1] == "Second sentence"

    def test_empty_segments(self):
        assert _merge_transcript_segments([]) == []

    def test_single_segment(self):
        result = _merge_transcript_segments([{"start": 0.0, "duration": 5.0, "text": "Only one"}])
        assert result == ["Only one"]

    def test_skips_empty_text(self):
        segments = [
            {"start": 0.0, "duration": 2.0, "text": "Real text"},
            {"start": 2.0, "duration": 1.0, "text": ""},
            {"start": 3.0, "duration": 2.0, "text": "More text"},
        ]
        result = _merge_transcript_segments(segments, gap_seconds=5.0)
        assert len(result) == 1
        assert "Real text" in result[0]
        assert "More text" in result[0]

    def test_object_segments(self):
        """Test with object-style segments (like youtube-transcript-api v1.x)."""
        class Segment:
            def __init__(self, start, duration, text):
                self.start = start
                self.duration = duration
                self.text = text

        segments = [
            Segment(0.0, 2.0, "Object segment one"),
            Segment(2.0, 2.0, "Object segment two"),
        ]
        result = _merge_transcript_segments(segments, gap_seconds=5.0)
        assert len(result) == 1
        assert "Object segment one" in result[0]


class TestTranscriptToDocuments:
    def test_basic_conversion(self):
        segments = [
            {"start": 0.0, "duration": 2.0, "text": "Hello world this is a test transcript"},
        ]
        docs = transcript_to_documents(
            video_id="testVid12345",
            segments=segments,
            lang="en",
            video_title="Test Video",
        )
        assert len(docs) >= 1
        assert docs[0]["id"].startswith("yt_testVid12345")
        assert docs[0]["metadata"]["source"] == "youtube"
        assert docs[0]["metadata"]["video_id"] == "testVid12345"
        assert docs[0]["metadata"]["language"] == "en"
        assert docs[0]["metadata"]["type"] == "youtube_transcript"

    def test_empty_transcript(self):
        docs = transcript_to_documents("vid", [], "en")
        assert docs == []

    def test_title_truncation(self):
        long_title = "A" * 300
        segments = [{"start": 0.0, "duration": 1.0, "text": "Content here"}]
        docs = transcript_to_documents("vid12345678", segments, "en", video_title=long_title)
        assert len(docs[0]["metadata"]["title"]) <= 200

    def test_multi_chunk_ids(self):
        # Create enough text to produce multiple chunks
        long_text = " ".join(["word"] * 2000)
        segments = [{"start": 0.0, "duration": 1.0, "text": long_text}]
        docs = transcript_to_documents("vid12345678", segments, "en", max_tokens=50, overlap=0)
        assert len(docs) > 1
        # Each doc should have a unique ID
        ids = [d["id"] for d in docs]
        assert len(ids) == len(set(ids))
        # IDs should include chunk index
        assert docs[0]["id"] == "yt_vid12345678_0"
        assert docs[1]["id"] == "yt_vid12345678_1"
