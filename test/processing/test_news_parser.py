from __future__ import annotations

from app.processing.news_parser import NewsParser
from app.exceptions import CrawlInputError


def _sample_crawl() -> dict:
    return {
        "start_url": "https://www.scmp.com/business",
        "crawl_depth": 2,
        "max_pages_per_level": 5,
        "summary": "sample",
        "crawl_time_utc": "2026-02-14T10:30:00Z",
        "parser_version": "1.0.0",
        "source_profile_name": "scmp",
        "pages": [
            {
                "url": "https://www.scmp.com/business",
                "title": "Business",
                "depth": 1,
                "meta": {"language": "en"},
                "headings": [
                    {"level": 2, "text": "Business"},
                    {"level": 2, "text": "Companies"},
                    {
                        "level": 2,
                        "text": "Meituan warns of US$3.5 billion loss amid intense food delivery price war",
                    },
                ],
                "text": "\n".join(
                    [
                        "Business",
                        "Companies",
                        "Exclusive",
                        "Meituan warns of US$3.5 billion loss amid intense food delivery price war",
                        "Margins and competition are under pressure",
                        "13 Feb 2026 - 10:15PM",
                        "The company flagged heavy subsidy pressure in major cities.",
                        "48",
                        "TRENDING TOPICS",
                        "MORE LATEST NEWS",
                    ]
                ),
            },
            {
                "url": "https://www.scmp.com/business/companies",
                "title": "Companies",
                "depth": 2,
                "meta": {"language": "en"},
                "headings": [],
                "text": "\n".join(
                    [
                        "Companies",
                        "Meituan warns of US$3.5 billion loss amid intense food delivery price war",
                        "13 Feb 2026 - 10:15PM",
                        "The company flagged heavy subsidy pressure in major cities and tier-2 cities.",
                        "Photo: Reuters",
                    ]
                ),
            },
        ],
    }


def test_news_parser_happy_path() -> None:
    parser = NewsParser()
    result = parser.parse(_sample_crawl())

    assert "feed_meta" in result
    assert result["feed_meta"]["stories_extracted"] == 1
    assert result["feed_meta"]["duplicates_removed"] == 1
    assert result["feed_meta"]["noise_lines_stripped"] >= 2

    story = result["stories"][0]
    assert story["headline"] == "Meituan warns of US$3.5 billion loss amid intense food delivery price war"
    assert story["subheadline"] == "Margins and competition are under pressure"
    assert story["section"] == "Companies"
    assert story["published_raw"] == "13 Feb 2026 - 10:15PM"
    assert story["published"].endswith("+08:00")
    assert story["content_type"] == "news"
    assert "exclusive" in story["tags"]
    assert story["comment_count"] == 48
    assert story["provenance"]["root_url"] == "https://www.scmp.com/business"
    assert story["provenance"]["page_url"] in {
        "https://www.scmp.com/business",
        "https://www.scmp.com/business/companies",
    }
    assert isinstance(story["parse_quality"]["parse_confidence"], float)


def test_news_parser_relative_time() -> None:
    parser = NewsParser()
    crawl = _sample_crawl()
    crawl["pages"][0]["text"] = "\n".join(
        [
            "Tech",
            "Chip exports surge amid demand rebound",
            "2 hours ago",
            "A rebound in consumer demand boosted exports.",
        ]
    )
    crawl["pages"] = [crawl["pages"][0]]

    result = parser.parse(crawl)
    assert result["feed_meta"]["stories_extracted"] == 1
    story = result["stories"][0]
    assert story["published"] is not None
    assert story["published"].startswith("2026-02-14T08:30:00")


def test_news_parser_missing_required_input_raises() -> None:
    parser = NewsParser()

    try:
        parser.parse({"pages": []})
    except CrawlInputError as exc:
        assert "start_url" in str(exc)
    else:
        raise AssertionError("Expected CrawlInputError")


def test_news_parser_pipe_headline_and_opinion() -> None:
    parser = NewsParser()
    crawl = _sample_crawl()
    crawl["pages"] = [
        {
            "url": "https://www.scmp.com/opinion",
            "title": "Opinion",
            "depth": 1,
            "meta": {"language": "en"},
            "headings": [],
            "text": "\n".join(
                [
                    "John Smith",
                    "Opinion",
                    "Opinion|Why supply chains are shifting faster than expected",
                    "13 Feb 2026 - 08:00PM",
                    "Businesses are adapting procurement strategy rapidly.",
                ]
            ),
        }
    ]

    result = parser.parse(crawl)
    story = result["stories"][0]
    assert story["headline"] == "Why supply chains are shifting faster than expected"
    assert story["section"] == "Opinion"
    assert story["content_type"] == "opinion"
    assert story["author"] == "John Smith"


def test_news_parser_parse_quality_flags_missing_fields() -> None:
    parser = NewsParser()
    crawl = _sample_crawl()
    crawl["pages"] = [
        {
            "url": "https://example.com/noisy",
            "title": "Noisy",
            "depth": 1,
            "meta": {},
            "headings": [],
            "text": "\n".join(
                [
                    "Unclear Headline",
                    "not-a-date",
                    "Details...",
                    "13 Feb 2026 - 10:15PM",
                ]
            ),
        }
    ]

    result = parser.parse(crawl)
    assert result["feed_meta"]["stories_extracted"] == 1
    quality = result["stories"][0]["parse_quality"]
    assert "section" in quality["missing_fields"]
    assert quality["parse_confidence"] < 1.0


def test_parser_accepts_single_page_wrapped_shape():
    """Contract test: parser accepts the shape _handle_get_content builds for depth=1.

    The MCP handler wraps a single-page result as:
        {"start_url": url, "pages": [page_data], "crawl_time_utc": ..., "parser_version": ...}
    Ensure the parser does not raise CrawlInputError on this shape.
    """
    parser = NewsParser()
    single_page = {
        "start_url": "https://example.com/article",
        "pages": [
            {
                "url": "https://example.com/article",
                "title": "Article Title",
                "text": "Article body text.",
                "success": True,
            }
        ],
        "crawl_time_utc": "2026-01-01T00:00:00Z",
        "parser_version": "1.0.0",
    }
    result = parser.parse(single_page)
    assert "feed_meta" in result
    assert result["feed_meta"]["pages_crawled"] == 1
    assert isinstance(result["stories"], list)
