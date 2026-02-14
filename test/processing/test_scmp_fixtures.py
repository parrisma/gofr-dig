"""Fixture-driven regression tests for NewsParser using realistic multi-page SCMP snapshots.

Each test exercises a distinct scenario that was either a past root-cause failure
or targets an under-covered code path in the pipeline.
"""

from __future__ import annotations

import pytest

from app.processing.news_parser import NewsParser

from .fixtures.scmp_snapshots import (
    scmp_business_multi_page,
    scmp_opinion_page,
    scmp_mixed_timestamps,
    scmp_empty_noisy_page,
    scmp_generic_fallback_crawl,
    scmp_depth_three_dedup_chain,
)


@pytest.fixture
def parser() -> NewsParser:
    return NewsParser()


# ── 1. Multi-page dedup, exclusive tags, sponsored filtering ────────────────


class TestBusinessMultiPage:
    """Five-page business crawl with cross-page duplicate (Meituan on pages 1+2),
    exclusive tag, sponsored story, noise stripping, and comment counts.
    """

    def test_story_count_after_dedup(self, parser: NewsParser) -> None:
        result = parser.parse(scmp_business_multi_page())
        meta = result["feed_meta"]
        # 5 pages, 5 stories, Meituan on 2 pages  →  1 duplicate removed
        assert meta["stories_extracted"] == 4
        assert meta["duplicates_removed"] == 1

    def test_exclusive_tag_applied(self, parser: NewsParser) -> None:
        result = parser.parse(scmp_business_multi_page())
        meituan = _find_story(result, "Meituan")
        assert meituan is not None
        assert "exclusive" in meituan["tags"]

    def test_sponsored_story_classified(self, parser: NewsParser) -> None:
        result = parser.parse(scmp_business_multi_page())
        sponsored = [s for s in result["stories"] if s["content_type"] == "sponsored"]
        assert len(sponsored) == 1
        assert "safeguard" in sponsored[0]["headline"].lower()

    def test_noise_lines_stripped(self, parser: NewsParser) -> None:
        result = parser.parse(scmp_business_multi_page())
        # TRENDING TOPICS + MORE LATEST NEWS + Photo:Reuters + Photo:Bloomberg
        assert result["feed_meta"]["noise_lines_stripped"] >= 3

    def test_comment_counts_extracted(self, parser: NewsParser) -> None:
        result = parser.parse(scmp_business_multi_page())
        meituan = _find_story(result, "Meituan")
        hsbc = _find_story(result, "HSBC")
        assert meituan is not None and meituan["comment_count"] == 48
        assert hsbc is not None and hsbc["comment_count"] == 103

    def test_sections_assigned(self, parser: NewsParser) -> None:
        result = parser.parse(scmp_business_multi_page())
        meituan = _find_story(result, "Meituan")
        hk_prices = _find_story(result, "home prices")
        hsbc = _find_story(result, "HSBC")
        assert meituan is not None and meituan["section"] == "Companies"
        assert hk_prices is not None and hk_prices["section"] == "Property"
        assert hsbc is not None and hsbc["section"] == "Banking & Finance"

    def test_deduped_story_keeps_seen_on_pages(self, parser: NewsParser) -> None:
        result = parser.parse(scmp_business_multi_page())
        meituan = _find_story(result, "Meituan")
        assert meituan is not None
        seen_urls = {p["page_url"] for p in meituan["seen_on_pages"]}
        assert "https://www.scmp.com/business" in seen_urls
        assert "https://www.scmp.com/business/companies/meituan" in seen_urls

    def test_winner_is_shallowest_depth(self, parser: NewsParser) -> None:
        result = parser.parse(scmp_business_multi_page())
        meituan = _find_story(result, "Meituan")
        assert meituan is not None
        # depth-1 page should win over depth-2
        assert meituan["provenance"]["crawl_depth"] == 1

    def test_pages_crawled_count(self, parser: NewsParser) -> None:
        result = parser.parse(scmp_business_multi_page())
        assert result["feed_meta"]["pages_crawled"] == 5

    def test_source_profile_in_meta(self, parser: NewsParser) -> None:
        result = parser.parse(scmp_business_multi_page())
        assert result["feed_meta"]["source_profile"] == "scmp"
        assert result["feed_meta"]["source_name"] == "South China Morning Post"


# ── 2. Opinion pipeline ────────────────────────────────────────────────────


class TestOpinionPage:
    """Three opinion pages: pipe-delimited headlines, author extraction,
    content_type classification, and Macroscope / As-I-see-it labels.
    """

    def test_three_opinion_stories_extracted(self, parser: NewsParser) -> None:
        result = parser.parse(scmp_opinion_page())
        assert result["feed_meta"]["stories_extracted"] == 3

    def test_pipe_headlines_cleaned(self, parser: NewsParser) -> None:
        result = parser.parse(scmp_opinion_page())
        headlines = {s["headline"] for s in result["stories"]}
        assert (
            "Why Asia's semiconductor future hinges on cooperation not rivalry"
            in headlines
        )
        assert "China's bond market is sending a deflation warning" in headlines
        assert "The hidden cost of AI regulation in Southeast Asia" in headlines

    def test_all_opinion_typed(self, parser: NewsParser) -> None:
        result = parser.parse(scmp_opinion_page())
        types = {s["content_type"] for s in result["stories"]}
        assert types == {"opinion"}

    def test_authors_extracted(self, parser: NewsParser) -> None:
        result = parser.parse(scmp_opinion_page())
        semiconductor = _find_story(result, "semiconductor")
        bond_market = _find_story(result, "bond market")
        ai_regulation = _find_story(result, "AI regulation")
        assert semiconductor is not None and semiconductor["author"] == "Jane Park"
        assert bond_market is not None and bond_market["author"] == "David Wei"
        assert ai_regulation is not None and ai_regulation["author"] == "Emily Chen"

    def test_opinion_sections_from_pipe(self, parser: NewsParser) -> None:
        result = parser.parse(scmp_opinion_page())
        semiconductor = _find_story(result, "semiconductor")
        bond_market = _find_story(result, "bond market")
        ai_regulation = _find_story(result, "AI regulation")
        assert semiconductor is not None and semiconductor["section"] == "Opinion"
        assert bond_market is not None and bond_market["section"] == "Macroscope"
        assert ai_regulation is not None and ai_regulation["section"] == "As I see it"

    def test_opinion_subheadlines(self, parser: NewsParser) -> None:
        result = parser.parse(scmp_opinion_page())
        semiconductor = _find_story(result, "semiconductor")
        assert semiconductor is not None
        assert (
            semiconductor["subheadline"]
            == "Building trust more important than building fabs"
        )


# ── 3. Mixed timestamp formats ─────────────────────────────────────────────


class TestMixedTimestamps:
    """One page per timestamp type: absolute, relative, unparseable."""

    def test_absolute_timestamp_parsed(self, parser: NewsParser) -> None:
        result = parser.parse(scmp_mixed_timestamps())
        huawei = _find_story(result, "Huawei")
        assert huawei is not None
        assert huawei["published"] is not None
        assert huawei["published"].startswith("2026-02-14T13:00:00")
        assert huawei["published"].endswith("+08:00")

    def test_relative_timestamp_resolved(self, parser: NewsParser) -> None:
        result = parser.parse(scmp_mixed_timestamps())
        bytedance = _find_story(result, "ByteDance")
        assert bytedance is not None
        assert bytedance["published"] is not None
        # crawl_time 14:00 UTC - 45 min = 13:15 UTC
        assert "2026-02-14T13:15:00" in bytedance["published"]

    def test_unparseable_date_page_produces_no_story(self, parser: NewsParser) -> None:
        """Samsung page has 'Updated: recently' which doesn't match any date
        pattern, so no date anchor is found → zero stories from that page.
        """
        result = parser.parse(scmp_mixed_timestamps())
        samsung = _find_story(result, "Samsung")
        # No date anchor means _segment_stories returns [] for this page
        assert samsung is None

    def test_two_stories_total(self, parser: NewsParser) -> None:
        result = parser.parse(scmp_mixed_timestamps())
        assert result["feed_meta"]["stories_extracted"] == 2


# ── 4. Noise-only page ─────────────────────────────────────────────────────


class TestEmptyNoisyPage:
    """A page composed entirely of noise markers should produce zero stories."""

    def test_zero_stories(self, parser: NewsParser) -> None:
        result = parser.parse(scmp_empty_noisy_page())
        assert result["feed_meta"]["stories_extracted"] == 0
        assert result["stories"] == []

    def test_noise_stripped(self, parser: NewsParser) -> None:
        result = parser.parse(scmp_empty_noisy_page())
        assert result["feed_meta"]["noise_lines_stripped"] >= 3


# ── 5. Generic fallback profile ────────────────────────────────────────────


class TestGenericFallback:
    """Crawl without source_profile_name uses generic profile."""

    def test_uses_generic_profile(self, parser: NewsParser) -> None:
        result = parser.parse(scmp_generic_fallback_crawl())
        assert result["feed_meta"]["source_profile"] == "generic"
        assert result["feed_meta"]["source_name"] == "Unknown Source"

    def test_two_stories_extracted(self, parser: NewsParser) -> None:
        result = parser.parse(scmp_generic_fallback_crawl())
        assert result["feed_meta"]["stories_extracted"] == 2

    def test_advertisement_noise_stripped(self, parser: NewsParser) -> None:
        result = parser.parse(scmp_generic_fallback_crawl())
        assert result["feed_meta"]["noise_lines_stripped"] >= 1

    def test_section_missing_lowers_confidence(self, parser: NewsParser) -> None:
        result = parser.parse(scmp_generic_fallback_crawl())
        # generic profile has no section_labels, so no section can be assigned
        for story in result["stories"]:
            if story["section"] is None:
                assert story["parse_quality"]["parse_confidence"] < 1.0
                assert "section" in story["parse_quality"]["missing_fields"]


# ── 6. Deep dedup chain (3 depths, same story, same section) ───────────────


class TestDepthThreeDedup:
    """Same story on 3 pages at different depths, identical section label.
    Should collapse to one story with 3 entries in seen_on_pages.
    """

    def test_single_story_after_dedup(self, parser: NewsParser) -> None:
        result = parser.parse(scmp_depth_three_dedup_chain())
        assert result["feed_meta"]["stories_extracted"] == 1
        assert result["feed_meta"]["duplicates_removed"] == 2

    def test_seen_on_three_pages(self, parser: NewsParser) -> None:
        result = parser.parse(scmp_depth_three_dedup_chain())
        story = result["stories"][0]
        assert len(story["seen_on_pages"]) == 3

    def test_shallowest_depth_wins(self, parser: NewsParser) -> None:
        result = parser.parse(scmp_depth_three_dedup_chain())
        story = result["stories"][0]
        assert story["provenance"]["crawl_depth"] == 1

    def test_headline_preserved(self, parser: NewsParser) -> None:
        result = parser.parse(scmp_depth_three_dedup_chain())
        assert (
            result["stories"][0]["headline"]
            == "China EV exports surge 40% in January"
        )


# ── 7. Feed-level structural integrity ─────────────────────────────────────


class TestFeedStructure:
    """Cross-cutting assertions on field completeness and ordering."""

    def test_stories_sorted_by_published_descending(self, parser: NewsParser) -> None:
        result = parser.parse(scmp_business_multi_page())
        published_values = [
            s["published"]
            for s in result["stories"]
            if s["published"] is not None
        ]
        assert published_values == sorted(published_values, reverse=True)

    def test_all_stories_have_story_id(self, parser: NewsParser) -> None:
        result = parser.parse(scmp_business_multi_page())
        for story in result["stories"]:
            assert story["story_id"]
            assert ":" in story["story_id"]

    def test_all_stories_have_provenance(self, parser: NewsParser) -> None:
        result = parser.parse(scmp_business_multi_page())
        for story in result["stories"]:
            prov = story["provenance"]
            assert prov["root_url"] == "https://www.scmp.com/business"
            assert prov["page_url"].startswith("https://www.scmp.com/")
            assert isinstance(prov["crawl_depth"], int)

    def test_language_populated(self, parser: NewsParser) -> None:
        result = parser.parse(scmp_business_multi_page())
        for story in result["stories"]:
            assert story["language"] == "en"

    def test_crawl_time_in_meta_is_iso_utc(self, parser: NewsParser) -> None:
        result = parser.parse(scmp_business_multi_page())
        ct = result["feed_meta"]["crawl_time_utc"]
        assert ct.endswith("Z")
        assert "2026-02-14" in ct

    def test_parser_version_in_meta(self, parser: NewsParser) -> None:
        result = parser.parse(scmp_business_multi_page())
        assert result["feed_meta"]["parser_version"] == "1.0.0"


# ── helpers ─────────────────────────────────────────────────────────────────


def _find_story(result: dict, keyword: str) -> dict | None:
    keyword_lower = keyword.lower()
    for story in result.get("stories", []):
        if keyword_lower in (story.get("headline") or "").lower():
            return story
    return None
