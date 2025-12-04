"""Scraping module for GOFR-DIG.

This module provides web scraping capabilities with anti-detection features,
content extraction using BeautifulSoup, and structure analysis tools.
"""

from app.scraping.antidetection import AntiDetectionManager, AntiDetectionProfile
from app.scraping.extractor import (
    ContentExtractor,
    ExtractedContent,
    extract_content,
    get_extractor,
)
from app.scraping.fetcher import FetchResult, HTTPFetcher, fetch_url, get_fetcher
from app.scraping.robots import (
    RobotsChecker,
    RobotsFile,
    RobotsParser,
    get_robots_checker,
    reset_robots_checker,
)
from app.scraping.state import ScrapingState, get_scraping_state, reset_scraping_state
from app.scraping.structure import (
    PageStructure,
    StructureAnalyzer,
    analyze_structure,
    get_analyzer,
)

__all__ = [
    "AntiDetectionManager",
    "AntiDetectionProfile",
    "ContentExtractor",
    "ExtractedContent",
    "FetchResult",
    "HTTPFetcher",
    "PageStructure",
    "RobotsChecker",
    "RobotsFile",
    "RobotsParser",
    "ScrapingState",
    "StructureAnalyzer",
    "analyze_structure",
    "extract_content",
    "fetch_url",
    "get_analyzer",
    "get_extractor",
    "get_fetcher",
    "get_robots_checker",
    "get_scraping_state",
    "reset_robots_checker",
    "reset_scraping_state",
]
