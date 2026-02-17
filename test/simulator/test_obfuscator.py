"""Tests for the obfuscator engine."""

from __future__ import annotations

from simulator.recording.obfuscator import (
    obfuscate,
    scrub_media,
    scrub_pii,
    scrub_text,
)


class TestScrubPII:
    """PII redaction tests."""

    def test_redacts_email_addresses(self):
        text = "Contact us at john.doe@example.com for info."
        result = scrub_pii(text)
        assert "john.doe@example.com" not in result
        assert "@" not in result
        # Length preserved
        assert len(result) == len(text)

    def test_redacts_multiple_emails(self):
        text = "alice@test.org and bob@company.co.uk are admins."
        result = scrub_pii(text)
        assert "alice@test.org" not in result
        assert "bob@company.co.uk" not in result

    def test_redacts_phone_numbers(self):
        text = "Call us at +1-800-555-1234 or (03) 9555-0123."
        result = scrub_pii(text)
        # Digits should be replaced with zeros, formatting preserved
        assert "555-1234" not in result
        assert "9555-0123" not in result

    def test_preserves_non_pii_text(self):
        text = "This is a normal sentence without PII."
        result = scrub_pii(text)
        assert result == text


class TestScrubText:
    """Text node replacement tests."""

    def test_replaces_visible_text_with_lorem(self):
        html = "<p>Hello World</p>"
        result = scrub_text(html)
        assert "<p>" in result
        assert "</p>" in result
        assert "Hello World" not in result

    def test_preserves_tag_structure(self):
        html = '<div class="article" id="main"><h1>Title</h1><p>Body text here.</p></div>'
        result = scrub_text(html)
        assert 'class="article"' in result
        assert 'id="main"' in result
        assert "<h1>" in result
        assert "</h1>" in result
        assert "<p>" in result
        assert "</p>" in result
        assert "Title" not in result
        assert "Body text here." not in result

    def test_preserves_script_content(self):
        html = "<script>var x = 42; console.log(x);</script>"
        result = scrub_text(html)
        assert "var x = 42; console.log(x);" in result

    def test_preserves_style_content(self):
        html = "<style>body { color: red; }</style>"
        result = scrub_text(html)
        assert "body { color: red; }" in result

    def test_preserves_whitespace_only_nodes(self):
        html = "<div>\n  <p>Text</p>\n</div>"
        result = scrub_text(html)
        assert "\n  " in result
        assert "\n" in result

    def test_preserves_html_comments(self):
        html = "<!-- This is a comment --><p>Content</p>"
        result = scrub_text(html)
        assert "<!-- This is a comment -->" in result

    def test_preserves_code_tag_content(self):
        html = "<code>import os</code>"
        result = scrub_text(html)
        assert "import os" in result

    def test_preserves_pre_tag_content(self):
        html = "<pre>  formatted\n  text</pre>"
        result = scrub_text(html)
        assert "  formatted\n  text" in result

    def test_deterministic_output(self):
        html = "<p>Same input produces same output.</p>"
        result1 = scrub_text(html)
        result2 = scrub_text(html)
        assert result1 == result2

    def test_handles_nested_tags(self):
        html = "<div><span><a href='/'>Link Text</a></span></div>"
        result = scrub_text(html)
        assert 'href="/"' in result
        assert "Link Text" not in result

    def test_handles_self_closing_tags(self):
        html = '<p>Before<br />After</p>'
        result = scrub_text(html)
        assert "<br />" in result

    def test_handles_entities(self):
        html = "<p>&copy; 2024</p>"
        result = scrub_text(html)
        assert "&copy;" in result


class TestScrubMedia:
    """Image placeholder tests."""

    def test_replaces_img_src(self):
        html = '<img src="https://example.com/photo.jpg" alt="Photo">'
        result = scrub_media(html)
        assert "example.com/photo.jpg" not in result
        assert "placeholder" in result
        assert 'alt="Photo"' in result

    def test_replaces_img_srcset(self):
        html = '<img src="a.jpg" srcset="b.jpg 2x, c.jpg 3x">'
        result = scrub_media(html)
        assert "a.jpg" not in result
        assert "b.jpg" not in result
        assert "c.jpg" not in result

    def test_leaves_non_img_tags_alone(self):
        html = '<a href="https://example.com">Link</a>'
        result = scrub_media(html)
        assert 'href="https://example.com"' in result

    def test_handles_single_quoted_src(self):
        html = "<img src='photo.png'>"
        result = scrub_media(html)
        assert "photo.png" not in result
        assert "placeholder" in result


class TestObfuscate:
    """Integration tests for the full pipeline."""

    def test_full_pipeline_on_simple_html(self):
        html = """<!DOCTYPE html>
<html>
<head><title>Test Page</title></head>
<body>
  <h1>Headlines Here</h1>
  <p>Contact john@example.com or call +1-555-123-4567.</p>
  <img src="https://cdn.example.com/image.jpg" alt="Photo">
  <script>var tracking = true;</script>
</body>
</html>"""
        result = obfuscate(html)

        # PII removed
        assert "john@example.com" not in result
        assert "555-123-4567" not in result

        # Original text replaced
        assert "Headlines Here" not in result
        assert "Contact" not in result

        # Structure preserved
        assert "<h1>" in result
        assert "</h1>" in result
        assert "<p>" in result
        assert "</p>" in result
        assert "<!DOCTYPE html>" in result

        # Script preserved
        assert "var tracking = true;" in result

        # Image replaced
        assert "cdn.example.com/image.jpg" not in result
        assert "placeholder" in result

    def test_result_is_valid_html_structure(self):
        html = "<html><body><div><p>Text</p></div></body></html>"
        result = obfuscate(html)
        # Should have matching tags
        assert result.count("<div>") == result.count("</div>")
        assert result.count("<p>") == result.count("</p>")

    def test_preserves_class_and_id_attributes(self):
        html = '<section class="news-article" id="article-42" data-category="finance"><p>Article body.</p></section>'
        result = obfuscate(html)
        assert 'class="news-article"' in result
        assert 'id="article-42"' in result
        assert 'data-category="finance"' in result

    def test_handles_empty_document(self):
        result = obfuscate("")
        assert result == ""

    def test_realistic_news_article(self):
        html = """<article class="story" data-id="12345">
  <h1>Breaking: Markets Rally on Trade Deal</h1>
  <p class="byline">By Jane Smith, jane.smith@newsorg.com</p>
  <p class="dateline">February 15, 2026</p>
  <div class="body">
    <p>Global stock markets surged today following the announcement
       of a landmark trade agreement. Call +81-3-1234-5678 for details.</p>
    <img src="https://cdn.newsorg.com/charts/sp500.png" alt="S&amp;P 500">
  </div>
</article>"""
        result = obfuscate(html)

        # Structure intact
        assert 'class="story"' in result
        assert 'data-id="12345"' in result
        assert 'class="byline"' in result
        assert 'class="body"' in result

        # Content gone
        assert "Breaking" not in result
        assert "Jane Smith" not in result
        assert "jane.smith@newsorg.com" not in result
        assert "Global stock markets" not in result

        # Image replaced
        assert "cdn.newsorg.com" not in result
