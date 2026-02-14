"""Realistic multi-page SCMP crawl snapshots for regression testing.

Each fixture function returns a fully-formed crawl-result dict that mirrors
the shape produced by get_content with crawl_depth >= 2.

Important: the parser segments stories by date-anchor — each block runs from
the previous date+1 to the next date.  On pages with multiple date lines the
blocks overlap, so fixtures intentionally keep ONE story per page (matching
real crawl output where sub-pages carry a single article).
"""

from __future__ import annotations


def scmp_business_multi_page() -> dict:
    """Five-page business crawl.

    Page 1 (hub, depth 1): Meituan story with exclusive tag.
    Page 2 (depth 2):      Meituan duplicate (same headline/date, richer body).
    Page 3 (depth 2):      HK home prices story with photo noise.
    Page 4 (depth 2):      HSBC story.
    Page 5 (depth 2):      Sponsored (retirement portfolio).
    """
    return {
        "start_url": "https://www.scmp.com/business",
        "crawl_depth": 2,
        "max_pages_per_level": 5,
        "summary": "SCMP business section crawl — 5 pages",
        "crawl_time_utc": "2026-02-14T12:00:00Z",
        "parser_version": "1.0.0",
        "source_profile_name": "scmp",
        "pages": [
            # ── Page 1: Hub / Meituan teaser (depth 1) ─────────────
            {
                "url": "https://www.scmp.com/business",
                "title": "Business | South China Morning Post",
                "depth": 1,
                "meta": {"language": "en"},
                "headings": [
                    {"level": 2, "text": "Business"},
                    {"level": 2, "text": "Companies"},
                ],
                "text": "\n".join([
                    "Business",
                    "Companies",
                    "Exclusive",
                    "Meituan warns of US$3.5 billion loss amid intense food"
                    " delivery price war",
                    "Margins squeezed as rivals undercut prices",
                    "13 Feb 2026 - 10:15PM",
                    "The company flagged heavy subsidy pressure in major cities.",
                    "48",
                    "TRENDING TOPICS",
                    "MORE LATEST NEWS",
                ]),
            },
            # ── Page 2: Meituan full article (depth 2, duplicate) ──
            {
                "url": "https://www.scmp.com/business/companies/meituan",
                "title": "Meituan warns of loss | SCMP",
                "depth": 2,
                "meta": {"language": "en"},
                "headings": [],
                "text": "\n".join([
                    "Companies",
                    "Meituan warns of US$3.5 billion loss amid intense food"
                    " delivery price war",
                    "Margins squeezed as rivals undercut prices",
                    "13 Feb 2026 - 10:15PM",
                    "The company flagged heavy subsidy pressure in major cities"
                    " and tier-2 cities.",
                    "Investors slashed their price targets on the stock.",
                    "Photo: Reuters",
                    "48",
                ]),
            },
            # ── Page 3: HK home prices (depth 2, unique) ──────────
            {
                "url": "https://www.scmp.com/business/property/hk-prices",
                "title": "Hong Kong home prices | SCMP",
                "depth": 2,
                "meta": {"language": "en"},
                "headings": [],
                "text": "\n".join([
                    "Property",
                    "Hong Kong home prices fall 4% in January",
                    "Analysts say more declines ahead without rate cuts",
                    "14 Feb 2026 - 07:30AM",
                    "Transactions in the secondary market were down 12%.",
                    "Photo: Bloomberg",
                    "22",
                ]),
            },
            # ── Page 4: HSBC restructuring (depth 2, unique) ──────
            {
                "url": "https://www.scmp.com/business/banking/hsbc",
                "title": "HSBC to cut jobs | SCMP",
                "depth": 2,
                "meta": {"language": "en"},
                "headings": [],
                "text": "\n".join([
                    "Banking & Finance",
                    "HSBC to cut 6,000 jobs in restructuring push",
                    "14 Feb 2026 - 06:45AM",
                    "CEO outlined a revised cost roadmap at the earnings call.",
                    "103",
                ]),
            },
            # ── Page 5: Sponsored content (depth 2) ───────────────
            {
                "url": "https://www.scmp.com/business/wealth/sponsored",
                "title": "Sponsored | SCMP",
                "depth": 2,
                "meta": {"language": "en"},
                "headings": [],
                "text": "\n".join([
                    "In partnership with:",
                    "How to safeguard your retirement portfolio",
                    "14 Feb 2026 - 12:00AM",
                    "Find out more about how to secure your future.",
                ]),
            },
        ],
    }


def scmp_opinion_page() -> dict:
    """Three opinion pages — one per columnist.

    Each page has a pipe-delimited headline, author name above the opinion
    label, and a subheadline.  Tests pipe extraction, opinion classification,
    author detection, and section assignment from pipe prefix.
    """
    return {
        "start_url": "https://www.scmp.com/opinion",
        "crawl_depth": 2,
        "max_pages_per_level": 5,
        "summary": "SCMP opinion section snapshot",
        "crawl_time_utc": "2026-02-14T12:00:00Z",
        "parser_version": "1.0.0",
        "source_profile_name": "scmp",
        "pages": [
            {
                "url": "https://www.scmp.com/opinion/semiconductors",
                "title": "Opinion | SCMP",
                "depth": 2,
                "meta": {"language": "en"},
                "headings": [],
                "text": "\n".join([
                    "Jane Park",
                    "Opinion",
                    "Opinion|Why Asia's semiconductor future hinges on"
                    " cooperation not rivalry",
                    "Building trust more important than building fabs",
                    "14 Feb 2026 - 09:00AM",
                    "Chip diplomacy is the new trade diplomacy.",
                ]),
            },
            {
                "url": "https://www.scmp.com/opinion/bonds",
                "title": "Macroscope | SCMP",
                "depth": 2,
                "meta": {"language": "en"},
                "headings": [],
                "text": "\n".join([
                    "David Wei",
                    "Macroscope",
                    "Macroscope|China's bond market is sending a deflation"
                    " warning",
                    "14 Feb 2026 - 07:15AM",
                    "The yield curve has flattened to levels not seen"
                    " since 2015.",
                ]),
            },
            {
                "url": "https://www.scmp.com/opinion/ai-regulation",
                "title": "As I see it | SCMP",
                "depth": 2,
                "meta": {"language": "en"},
                "headings": [],
                "text": "\n".join([
                    "Emily Chen",
                    "As I see it",
                    "As I see it|The hidden cost of AI regulation in"
                    " Southeast Asia",
                    "Startups bear the brunt of compliance overhead",
                    "13 Feb 2026 - 11:30PM",
                    "Governments should consider tiered approaches.",
                    "7",
                ]),
            },
        ],
    }


def scmp_mixed_timestamps() -> dict:
    """Three pages testing different timestamp formats:

    Page 1: absolute timestamp ("14 Feb 2026 - 01:00PM").
    Page 2: relative timestamp ("45 minutes ago").
    Page 3: unparseable timestamp ("Updated: recently") → DATE_PARSE_FAILED.
    """
    return {
        "start_url": "https://www.scmp.com/tech",
        "crawl_depth": 2,
        "max_pages_per_level": 5,
        "summary": "SCMP tech with mixed date formats",
        "crawl_time_utc": "2026-02-14T14:00:00Z",
        "parser_version": "1.0.0",
        "source_profile_name": "scmp",
        "pages": [
            {
                "url": "https://www.scmp.com/tech/huawei",
                "title": "Tech | SCMP",
                "depth": 2,
                "meta": {"language": "en"},
                "headings": [],
                "text": "\n".join([
                    "Tech",
                    "Huawei reveals new cloud chip for AI inference workloads",
                    "Ascend 920 targets inference at the edge",
                    "14 Feb 2026 - 01:00PM",
                    "The chip is fabricated at SMIC's 7nm process node.",
                ]),
            },
            {
                "url": "https://www.scmp.com/tech/bytedance",
                "title": "Tech | SCMP",
                "depth": 2,
                "meta": {"language": "en"},
                "headings": [],
                "text": "\n".join([
                    "Tech",
                    "ByteDance launches open-source video model",
                    "45 minutes ago",
                    "The model supports 1080p generation in under 10 seconds.",
                ]),
            },
            {
                "url": "https://www.scmp.com/tech/samsung",
                "title": "Tech | SCMP",
                "depth": 2,
                "meta": {"language": "en"},
                "headings": [],
                "text": "\n".join([
                    "Tech",
                    "Samsung foldable shipments beat forecasts",
                    "Updated: recently",
                    "Galaxy Z Fold8 demand was stronger than expected.",
                ]),
            },
        ],
    }


def scmp_empty_noisy_page() -> dict:
    """Page that is entirely noise — should produce zero stories."""
    return {
        "start_url": "https://www.scmp.com/404",
        "crawl_depth": 1,
        "max_pages_per_level": 1,
        "summary": "Pure noise page",
        "crawl_time_utc": "2026-02-14T12:00:00Z",
        "parser_version": "1.0.0",
        "source_profile_name": "scmp",
        "pages": [
            {
                "url": "https://www.scmp.com/404",
                "title": "Page Not Found",
                "depth": 1,
                "meta": {},
                "headings": [],
                "text": "\n".join([
                    "TRENDING TOPICS",
                    "MORE LATEST NEWS",
                    "Photo: AFP",
                    "MOST POPULAR",
                    "Illustration: SCMP Graphics",
                ]),
            },
        ],
    }


def scmp_generic_fallback_crawl() -> dict:
    """Crawl with NO source_profile_name — forces generic fallback profile.

    Two pages with one story each. Should parse but with lower confidence
    because section labels are not recognised by the generic profile.
    """
    return {
        "start_url": "https://www.example-news.com/world",
        "crawl_depth": 2,
        "max_pages_per_level": 3,
        "summary": "Unknown news site",
        "crawl_time_utc": "2026-02-14T12:00:00Z",
        "parser_version": "1.0.0",
        "pages": [
            {
                "url": "https://www.example-news.com/world/trade",
                "title": "World",
                "depth": 2,
                "meta": {"language": "en"},
                "headings": [],
                "text": "\n".join([
                    "Global trade tensions rise as tariffs loom",
                    "14 Feb 2026 - 09:00AM",
                    "The US has signalled a new round of tariffs on EU goods.",
                    "ADVERTISEMENT",
                ]),
            },
            {
                "url": "https://www.example-news.com/world/earthquake",
                "title": "World",
                "depth": 2,
                "meta": {"language": "en"},
                "headings": [],
                "text": "\n".join([
                    "Earthquake hits southern Turkey",
                    "13 Feb 2026 - 11:00PM",
                    "The quake measured 5.6 on the Richter scale.",
                ]),
            },
        ],
    }


def scmp_depth_three_dedup_chain() -> dict:
    """Same story appears on 3 pages at depths 1, 2, 3 — all under the same
    section label so dedupe keys match.  Should collapse to one story with
    3 entries in seen_on_pages.
    """
    headline = "China EV exports surge 40% in January"
    date_str = "14 Feb 2026 - 10:00AM"

    def _make_page(url: str, depth: int, extra_body: str = "") -> dict:
        lines = ["Companies", headline, date_str]
        if extra_body:
            lines.append(extra_body)
        return {
            "url": url,
            "title": "Companies",
            "depth": depth,
            "meta": {"language": "en"},
            "headings": [],
            "text": "\n".join(lines),
        }

    return {
        "start_url": "https://www.scmp.com/business",
        "crawl_depth": 3,
        "max_pages_per_level": 5,
        "summary": "Deep dedup chain",
        "crawl_time_utc": "2026-02-14T12:00:00Z",
        "parser_version": "1.0.0",
        "source_profile_name": "scmp",
        "pages": [
            _make_page("https://www.scmp.com/business", 1),
            _make_page(
                "https://www.scmp.com/business/companies", 2,
                "BYD and NIO led the market.",
            ),
            _make_page(
                "https://www.scmp.com/business/companies/ev", 3,
                "BYD and NIO led the market. European OEMs expressed concern.",
            ),
        ],
    }
