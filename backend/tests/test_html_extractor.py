"""Tests for readable-text and title extraction from synthetic HTML."""

from __future__ import annotations

from app.services.html_extractor import extract_page


def test_extracts_page_title() -> None:
    html = """
    <html><head><title>  My Article Title  </title></head>
    <body><article><p>Article body text.</p></article></body></html>
    """

    page = extract_page(html)

    assert page.title == "My Article Title"
    assert "Article body text." in page.text


def test_title_falls_back_to_open_graph_meta() -> None:
    html = """
    <html><head>
      <meta property="og:title" content="Open Graph Headline" />
    </head><body><main><p>Body.</p></main></body></html>
    """

    assert extract_page(html).title == "Open Graph Headline"


def test_title_falls_back_to_twitter_meta_then_h1() -> None:
    twitter_html = (
        '<html><head><meta name="twitter:title" content="Tweet Title"></head>'
        "<body><p>Body.</p></body></html>"
    )
    h1_html = "<html><body><h1>Heading Title</h1><p>Body.</p></body></html>"

    assert extract_page(twitter_html).title == "Tweet Title"
    assert extract_page(h1_html).title == "Heading Title"


def test_extracts_headings_paragraphs_and_list_items() -> None:
    html = """
    <html><body><article>
      <h1>Main Heading</h1>
      <h2>Section Heading</h2>
      <p>First paragraph with useful detail.</p>
      <p>Second paragraph with more detail.</p>
      <ul><li>List item one</li><li>List item two</li></ul>
      <blockquote>A quoted passage.</blockquote>
    </article></body></html>
    """

    text = extract_page(html).text

    for expected in (
        "Main Heading",
        "Section Heading",
        "First paragraph with useful detail.",
        "Second paragraph with more detail.",
        "List item one",
        "List item two",
        "A quoted passage.",
    ):
        assert expected in text


def test_removes_script_and_style_content() -> None:
    html = """
    <html><head>
      <title>Clean</title>
      <style>.secret { color: red; }</style>
      <script>var secret = 'do not show me';</script>
    </head><body><article><p>Visible text.</p></article></body></html>
    """

    page = extract_page(html)

    assert "Visible text." in page.text
    assert "secret" not in page.text
    assert "color: red" not in page.text


def test_removes_navigation_footer_header_and_aside() -> None:
    html = """
    <html><body>
      <header>Site header noise</header>
      <nav>Link one Link two Link three</nav>
      <aside>Related stories noise</aside>
      <main><p>Real article content.</p></main>
      <footer>Copyright noise</footer>
    </body></html>
    """

    text = extract_page(html).text

    assert "Real article content." in text
    for noise in ("Site header noise", "Link one", "Related stories noise", "Copyright noise"):
        assert noise not in text


def test_removes_advertisement_and_cookie_markup() -> None:
    html = """
    <html><body><article>
      <div class="advertisement">BUY THIS NOW</div>
      <div id="cookie-banner">We use cookies</div>
      <div class="social-share">Share on social media</div>
      <p>Genuine paragraph.</p>
    </article></body></html>
    """

    text = extract_page(html).text

    assert "Genuine paragraph." in text
    for noise in ("BUY THIS NOW", "We use cookies", "Share on social media"):
        assert noise not in text


def test_prefers_article_then_main_content() -> None:
    article_html = """
    <html><body>
      <main><p>Main content.</p></main>
      <article><p>Article content.</p></article>
    </body></html>
    """
    main_only_html = "<html><body><main><p>Main content.</p></main></body></html>"

    assert "Article content." in extract_page(article_html).text
    assert "Main content." not in extract_page(article_html).text
    assert "Main content." in extract_page(main_only_html).text


def test_deduplicates_repeated_blocks() -> None:
    html = """
    <html><body><main>
      <p>Repeated sentence.</p>
      <p>Repeated sentence.</p>
      <p>Repeated   sentence.</p>
      <p>A different sentence.</p>
    </main></body></html>
    """

    text = extract_page(html).text

    assert text.count("Repeated sentence.") == 1
    assert "A different sentence." in text


def test_malformed_html_is_tolerated() -> None:
    html = "<html><body><article><p>Unclosed paragraph<h2>Another heading<p>More text"

    page = extract_page(html)

    assert "Unclosed paragraph" in page.text
    assert "Another heading" in page.text


def test_empty_html_returns_empty_text_and_no_title() -> None:
    page = extract_page("")

    assert page.title is None
    assert page.text == ""


def test_html_with_no_text_tags_falls_back_to_body_text() -> None:
    page = extract_page("<html><body><div>Plain div text without paragraphs</div></body></html>")

    assert page.text == "Plain div text without paragraphs"


def test_unicode_content_is_preserved() -> None:
    html = """
    <html><head><title>Café — 日本語</title></head><body><article>
      <p>Node.js — naïve café, emoji 🚀, и текст.</p>
    </article></body></html>
    """

    page = extract_page(html)

    assert page.title == "Café — 日本語"
    assert "naïve café, emoji 🚀, и текст." in page.text
