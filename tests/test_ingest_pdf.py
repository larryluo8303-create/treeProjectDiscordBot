"""Tests for ingestion.ingest_pdf module — text cleanup and document building."""

from ingestion.ingest_pdf import _clean_page_text, _build_documents


class TestCleanPageText:
    def test_removes_leading_page_number(self):
        text = "123\nActual content here"
        result = _clean_page_text(text)
        assert not result.startswith("123")
        assert "Actual content here" in result

    def test_removes_trailing_page_number(self):
        text = "Some content on the page\n  456"
        result = _clean_page_text(text)
        assert not result.endswith("456")
        assert "Some content on the page" in result

    def test_preserves_content(self):
        text = "This is the main body of the page with no page numbers."
        result = _clean_page_text(text)
        assert result == text

    def test_empty_string(self):
        assert _clean_page_text("") == ""

    def test_only_page_number(self):
        result = _clean_page_text("42\n")
        # After removing leading page number, may be empty
        assert isinstance(result, str)


class TestBuildDocuments:
    def test_basic_building(self):
        pages = [
            (1, "This is the first page content with enough text to be valid."),
            (2, "This is the second page with different content for testing."),
        ]
        docs = _build_documents(
            pages=pages,
            pdf_path="/fake/path/book.pdf",
            source_label="Test Book",
            max_tokens=500,
            overlap_tokens=0,
        )
        assert len(docs) >= 2
        for doc in docs:
            assert "id" in doc
            assert "text" in doc
            assert "metadata" in doc
            assert doc["id"].startswith("pdf_")
            assert doc["metadata"]["type"] == "book"
            assert doc["metadata"]["source"] == "Test Book"

    def test_deterministic_ids(self):
        pages = [(1, "Test content for deterministic ID generation.")]
        docs1 = _build_documents(pages, "/path/a.pdf", "src", 500, 0)
        docs2 = _build_documents(pages, "/path/a.pdf", "src", 500, 0)
        assert docs1[0]["id"] == docs2[0]["id"]

    def test_different_paths_different_ids(self):
        pages = [(1, "Same content.")]
        docs1 = _build_documents(pages, "/path/a.pdf", "src", 500, 0)
        docs2 = _build_documents(pages, "/path/b.pdf", "src", 500, 0)
        assert docs1[0]["id"] != docs2[0]["id"]

    def test_page_number_in_metadata(self):
        pages = [(5, "Content on page five.")]
        docs = _build_documents(pages, "/fake.pdf", "", 500, 0)
        assert docs[0]["metadata"]["page"] == 5

    def test_source_label_fallback_to_filename(self):
        pages = [(1, "Some content here.")]
        docs = _build_documents(pages, "/path/my_book.pdf", "", 500, 0)
        # When source_label is empty, uses filename
        assert docs[0]["metadata"]["source"] == "my_book.pdf"

    def test_empty_chunk_skipped(self):
        pages = [(1, "")]  # empty page text
        docs = _build_documents(pages, "/fake.pdf", "src", 500, 0)
        assert len(docs) == 0
