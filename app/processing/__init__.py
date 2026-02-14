"""Post-processing module for gofr-dig crawl output."""

from app.processing.source_profiles import (
    SOURCE_PROFILES,
    GENERIC_PROFILE,
    get_source_profile,
)
from app.processing.news_parser import NewsParser

__all__ = [
    "NewsParser",
    "SOURCE_PROFILES",
    "GENERIC_PROFILE",
    "get_source_profile",
]
