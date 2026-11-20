"""Tests for bounded context construction and citation/source mapping."""

from __future__ import annotations

from app.models import SourceType
from app.services.context import build_context
from tests.rag_helpers import make_result


def test_build_context_numbers_citations_and_preserves_source_metadata() -> None:
    results = [
        make_result(
            item_id=11,
            title="Node.js notes",
            text="Node.js is a JavaScript runtime.",
            source_type=SourceType.URL,
            source_url="https://example.com/node",
        ),
        make_result(item_id=12, title="Database notes", text="Chroma stores vectors."),
    ]

    context = build_context(results, max_chars=5_000)

    assert [source.citation_id for source in context.sources] == ["[1]", "[2]"]
    assert "[1] Item ID: 11" in context.text
    assert "Title: Node.js notes" in context.text
    assert "Source URL: https://example.com/node" in context.text
    assert "Excerpt: Node.js is a JavaScript runtime." in context.text
    assert "Excerpt: Chroma stores vectors." in context.text

    first, second = context.sources
    assert first.knowledge_item.id == 11
    assert first.knowledge_item.source_type is SourceType.URL
    assert first.knowledge_item.source_url == "https://example.com/node"
    assert first.snippet == "Node.js is a JavaScript runtime."
    assert second.knowledge_item.id == 12
    assert second.citation_id == "[2]"


def test_build_context_respects_the_character_budget() -> None:
    results = [make_result(item_id=1, text="x" * 5_000)]

    context = build_context(results, max_chars=300)

    assert len(context.text) <= 300
    assert [source.citation_id for source in context.sources] == ["[1]"]
    assert len(context.sources[0].snippet) < 5_000
    assert "Excerpt:" in context.text


def test_build_context_stops_before_uncited_overflow_sources() -> None:
    results = [
        make_result(item_id=1, title="First", text="a" * 5_000),
        make_result(item_id=2, title="Second", text="b" * 5_000),
    ]

    context = build_context(results, max_chars=350)

    assert len(context.text) <= 350
    assert [source.citation_id for source in context.sources] == ["[1]"]
    assert "Second" not in context.text
    assert "b" not in context.text


def test_build_context_with_no_results_is_empty() -> None:
    context = build_context([])

    assert context.text == ""
    assert context.sources == ()
