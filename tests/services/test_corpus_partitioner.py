"""Stage 2 corpus chunker tests."""

from platform_service.config import get_settings
from platform_service.services.corpus_partitioner import (
    chunk_by_token_budget,
    estimate_corpus_tokens,
)


def _make_corpus(doc_id: str, pages: list[tuple[int, list[str]]]) -> list[dict]:
    """Build a page_corpus from `(page_number, [block_texts])` tuples."""
    return [
        {
            "source_document_id": doc_id,
            "content_domain": "clinical",
            "primary_language": "en",
            "pages": [
                {
                    "page_number": pn,
                    "source_page_id": f"{doc_id}-p{pn}",
                    "blocks": [
                        {
                            "content_block_id": f"{doc_id}-p{pn}-b{i}",
                            "block_type": "paragraph",
                            "content_text": text,
                        }
                        for i, text in enumerate(blocks)
                    ],
                }
                for pn, blocks in pages
            ],
        }
    ]


class TestTokenEstimate:
    def test_empty_corpus_zero(self) -> None:
        assert estimate_corpus_tokens([]) == 0

    def test_sums_across_documents(self) -> None:
        corpus = [
            {
                "source_document_id": "d1",
                "pages": [{"blocks": [{"content_text": "x" * 400}, {"content_text": "y" * 400}]}],
            },
            {
                "source_document_id": "d2",
                "pages": [{"blocks": [{"content_text": "z" * 400}]}],
            },
        ]
        # 400 chars ≈ 100 tokens; total ≈ 300
        total = estimate_corpus_tokens(corpus)
        assert 200 <= total <= 350


class TestChunkByTokenBudget:
    def test_small_corpus_one_chunk(self) -> None:
        # Tiny corpus, well under target — should produce one chunk.
        corpus = _make_corpus("d1", [(1, ["short"]), (2, ["alsoshort"])])
        chunks = chunk_by_token_budget(corpus, document_outlines=[])
        assert len(chunks) == 1
        assert chunks[0].page_range == (1, 2)
        assert chunks[0].chunk_id == "chunk-1"

    def test_large_corpus_multiple_chunks(self, monkeypatch) -> None:
        # Each page ~80K tokens (320K chars). Target 60K. With no outline
        # boundaries, chunker breaks once current_tokens >= target.
        s = get_settings()
        monkeypatch.setattr(s, "stage_c_chunk_target_tokens", 60_000)
        monkeypatch.setattr(s, "stage_c_chunk_window_pct", 0.10)

        big = "x" * 320_000  # ~80K tokens
        corpus = _make_corpus("d1", [(1, [big]), (2, [big]), (3, [big]), (4, [big])])
        chunks = chunk_by_token_budget(corpus, document_outlines=[])
        # Each page alone exceeds target → each becomes its own chunk.
        assert len(chunks) == 4
        # Pages are content-disjoint across chunks.
        all_pages = []
        for c in chunks:
            for doc in c.page_corpus:
                all_pages.extend(p["page_number"] for p in doc["pages"])
        assert sorted(all_pages) == [1, 2, 3, 4]

    def test_snaps_to_outline_boundary(self, monkeypatch) -> None:
        s = get_settings()
        monkeypatch.setattr(s, "stage_c_chunk_target_tokens", 100)
        monkeypatch.setattr(s, "stage_c_chunk_window_pct", 0.50)

        # 6 pages, each ~30 tokens. Target 100. Outline boundary at page 3.
        # Expected: chunk 1 = pages 1-2 (60 tokens), chunk 2 starts at page 3.
        corpus = _make_corpus(
            "d1",
            [
                (1, ["x" * 120]),  # ~30 tokens
                (2, ["x" * 120]),
                (3, ["x" * 120]),
                (4, ["x" * 120]),
                (5, ["x" * 120]),
                (6, ["x" * 120]),
            ],
        )
        outlines = [
            {
                "source_document_id": "d1",
                "sections": [
                    {"section_id": "s1", "page_range": [1, 2]},
                    {"section_id": "s2", "page_range": [3, 6]},
                ],
            }
        ]
        chunks = chunk_by_token_budget(corpus, outlines)
        # Should break at page 3 (outline boundary).
        assert len(chunks) >= 2
        # First chunk should cover early pages; subsequent chunk starts at 3+
        assert chunks[0].page_range[0] == 1
        # No page appears twice.
        all_pages = []
        for c in chunks:
            for doc in c.page_corpus:
                all_pages.extend(p["page_number"] for p in doc["pages"])
        assert len(all_pages) == len(set(all_pages))

    def test_empty_corpus_no_chunks(self) -> None:
        assert chunk_by_token_budget([], document_outlines=[]) == []
