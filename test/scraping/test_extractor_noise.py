"""Tests for noise-filtering in ContentExtractor.

Validates that filter_noise strips ad elements and noise text lines
from extracted content.
"""

from app.scraping.extractor import ContentExtractor, extract_content


# -------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------

BASIC_HTML = """\
<html>
<head><title>Test Page</title></head>
<body>
  <div id="main-content">
    <h1>Hello World</h1>
    <p>This is useful content.</p>
  </div>
  <div class="ad-container">
    <p>Buy our stuff!</p>
  </div>
  <div id="sidebar-advertisement">
    <p>Sponsored link</p>
  </div>
</body>
</html>
"""

AD_CLASS_HTML = """\
<html><body>
  <p>Real article text.</p>
  <div class="adslot-wrapper"><p>Ad slot content</p></div>
  <div class="taboola-below-article"><p>Taboola junk</p></div>
  <div class="outbrain-widget"><p>Outbrain junk</p></div>
  <p>More real text.</p>
</body></html>
"""

NOISE_TEXT_HTML = """\
<html><body>
<p>Good intro paragraph.</p>
<p>Advertisement</p>
<p>Another good paragraph.</p>
<p>Sponsored Content</p>
<p>We use cookies</p>
<p>Subscribe now</p>
<p>MULTIMEDIA</p>
<p>Video</p>
<p>videocam</p>
<p>+ FOLLOW</p>
<p>Share this</p>
<p>Read more</p>
<p>Related stories</p>
<p>Comments</p>
<p>-</p>
<p>Final good paragraph.</p>
</body></html>
"""

NO_NOISE_HTML = """\
<html><body>
<h1>Clean Article</h1>
<p>Paragraph one with no ads.</p>
<p>Paragraph two is also clean.</p>
</body></html>
"""


# -------------------------------------------------------------------
# Tests: HTML-level ad element removal
# -------------------------------------------------------------------

class TestAdElementRemoval:
    """Verify that ad-related HTML elements are stripped."""

    def test_ad_container_removed(self):
        extractor = ContentExtractor()
        result = extractor.extract(BASIC_HTML, filter_noise=True)
        assert "Buy our stuff" not in result.text
        assert "Hello World" in result.text

    def test_ad_id_removed(self):
        extractor = ContentExtractor()
        result = extractor.extract(BASIC_HTML, filter_noise=True)
        assert "Sponsored link" not in result.text

    def test_ad_elements_kept_when_filter_off(self):
        extractor = ContentExtractor()
        result = extractor.extract(BASIC_HTML, filter_noise=False)
        assert "Buy our stuff" in result.text

    def test_taboola_outbrain_removed(self):
        extractor = ContentExtractor()
        result = extractor.extract(AD_CLASS_HTML, filter_noise=True)
        assert "Taboola junk" not in result.text
        assert "Outbrain junk" not in result.text
        assert "Ad slot content" not in result.text
        assert "Real article text" in result.text
        assert "More real text" in result.text

    def test_taboola_outbrain_kept_when_filter_off(self):
        extractor = ContentExtractor()
        result = extractor.extract(AD_CLASS_HTML, filter_noise=False)
        assert "Taboola junk" in result.text


# -------------------------------------------------------------------
# Tests: text-level noise line filtering
# -------------------------------------------------------------------

class TestNoiseTextFiltering:
    """Verify that noise text lines are stripped from output."""

    def test_advertisement_line_removed(self):
        extractor = ContentExtractor()
        result = extractor.extract(NOISE_TEXT_HTML, filter_noise=True)
        assert "Advertisement" not in result.text
        assert "Good intro paragraph" in result.text
        assert "Another good paragraph" in result.text
        assert "Final good paragraph" in result.text

    def test_sponsored_content_removed(self):
        extractor = ContentExtractor()
        result = extractor.extract(NOISE_TEXT_HTML, filter_noise=True)
        assert "Sponsored Content" not in result.text

    def test_cookie_notice_removed(self):
        extractor = ContentExtractor()
        result = extractor.extract(NOISE_TEXT_HTML, filter_noise=True)
        assert "We use cookies" not in result.text

    def test_subscribe_prompt_removed(self):
        extractor = ContentExtractor()
        result = extractor.extract(NOISE_TEXT_HTML, filter_noise=True)
        assert "Subscribe now" not in result.text

    def test_multimedia_label_removed(self):
        extractor = ContentExtractor()
        result = extractor.extract(NOISE_TEXT_HTML, filter_noise=True)
        assert "MULTIMEDIA" not in result.text

    def test_video_label_removed(self):
        extractor = ContentExtractor()
        result = extractor.extract(NOISE_TEXT_HTML, filter_noise=True)
        # Standalone "Video" line removed, but not embedded in sentences
        for line in result.text.split("\n"):
            assert line.strip() != "Video"
            assert line.strip() != "videocam"

    def test_follow_removed(self):
        extractor = ContentExtractor()
        result = extractor.extract(NOISE_TEXT_HTML, filter_noise=True)
        for line in result.text.split("\n"):
            assert line.strip() != "+ FOLLOW"

    def test_share_removed(self):
        extractor = ContentExtractor()
        result = extractor.extract(NOISE_TEXT_HTML, filter_noise=True)
        for line in result.text.split("\n"):
            assert line.strip() != "Share this"

    def test_read_more_removed(self):
        extractor = ContentExtractor()
        result = extractor.extract(NOISE_TEXT_HTML, filter_noise=True)
        for line in result.text.split("\n"):
            assert line.strip() != "Read more"

    def test_related_stories_removed(self):
        extractor = ContentExtractor()
        result = extractor.extract(NOISE_TEXT_HTML, filter_noise=True)
        for line in result.text.split("\n"):
            assert line.strip() != "Related stories"

    def test_comments_removed(self):
        extractor = ContentExtractor()
        result = extractor.extract(NOISE_TEXT_HTML, filter_noise=True)
        for line in result.text.split("\n"):
            assert line.strip() != "Comments"

    def test_standalone_punctuation_removed(self):
        extractor = ContentExtractor()
        result = extractor.extract(NOISE_TEXT_HTML, filter_noise=True)
        for line in result.text.split("\n"):
            assert line.strip() != "-"

    def test_video_in_sentence_kept(self):
        """Ensure 'video' inside a real sentence is NOT stripped."""
        html = '<html><body><p>This video explains the topic well.</p></body></html>'
        extractor = ContentExtractor()
        result = extractor.extract(html, filter_noise=True)
        assert "video explains" in result.text

    def test_noise_kept_when_filter_off(self):
        extractor = ContentExtractor()
        result = extractor.extract(NOISE_TEXT_HTML, filter_noise=False)
        assert "Advertisement" in result.text

    def test_clean_html_unchanged(self):
        extractor = ContentExtractor()
        with_filter = extractor.extract(NO_NOISE_HTML, filter_noise=True)
        without_filter = extractor.extract(NO_NOISE_HTML, filter_noise=False)
        assert with_filter.text == without_filter.text
        assert "Clean Article" in with_filter.text


# -------------------------------------------------------------------
# Tests: extract_by_selector with filter_noise
# -------------------------------------------------------------------

class TestSelectorWithNoise:
    """Verify noise filtering works with CSS selector extraction."""

    HTML = """\
    <html><body>
      <div id="content">
        <p>Real content.</p>
        <p>Advertisement</p>
        <div class="adslot"><p>Hidden ad</p></div>
        <p>More real content.</p>
      </div>
    </body></html>
    """

    def test_selector_filters_noise(self):
        extractor = ContentExtractor()
        result = extractor.extract_by_selector(
            self.HTML, "#content", filter_noise=True,
        )
        assert "Real content" in result.text
        assert "More real content" in result.text
        assert "Hidden ad" not in result.text
        assert "Advertisement" not in result.text

    def test_selector_keeps_noise_when_off(self):
        extractor = ContentExtractor()
        result = extractor.extract_by_selector(
            self.HTML, "#content", filter_noise=False,
        )
        assert "Advertisement" in result.text


# -------------------------------------------------------------------
# Tests: extract_main_content with filter_noise
# -------------------------------------------------------------------

class TestMainContentWithNoise:
    """Verify noise filtering works with main content extraction."""

    HTML = """\
    <html><body>
      <main>
        <p>Article body.</p>
        <p>Advertisement</p>
        <div class="sponsored"><p>Sponsor block</p></div>
      </main>
    </body></html>
    """

    def test_main_content_filters_noise(self):
        extractor = ContentExtractor()
        result = extractor.extract_main_content(self.HTML, filter_noise=True)
        assert "Article body" in result.text
        assert "Sponsor block" not in result.text
        assert "Advertisement" not in result.text


# -------------------------------------------------------------------
# Tests: convenience function
# -------------------------------------------------------------------

class TestConvenienceFunction:
    """Verify extract_content passes filter_noise through."""

    def test_convenience_filters_noise(self):
        result = extract_content(NOISE_TEXT_HTML, filter_noise=True)
        assert "Advertisement" not in result.text
        assert "Good intro paragraph" in result.text

    def test_convenience_no_filter(self):
        result = extract_content(NOISE_TEXT_HTML, filter_noise=False)
        assert "Advertisement" in result.text
