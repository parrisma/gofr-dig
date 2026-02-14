"""News parser exceptions for GOFR-DIG.

Each exception includes root cause context and remediation guidance
to support structured error handling and actionable diagnostics.
"""

from typing import Any

from gofr_common.exceptions import GofrError, ValidationError


class NewsParserError(GofrError):
    """Base exception for all news parser failures.

    Root cause: a parser pipeline step failed in a way that prevents
    producing a valid feed output.
    Remediation: inspect the nested cause and the specific subclass for guidance.
    """

    default_code = "NEWS_PARSER"

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(code=self.default_code, message=message, details=details)


class CrawlInputError(ValidationError):
    """Raised when the crawl_result dict is missing required structure.

    Root cause: the input to NewsParser.parse() does not contain the expected
    keys (e.g. missing 'pages', missing 'start_url').
    Remediation: ensure the crawl_result is a well-formed get_content output dict
    containing at minimum 'start_url' and 'pages' keys.
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(code="CRAWL_INPUT", message=message, details=details)


class SourceProfileError(ValidationError):
    """Raised when a source profile is invalid or contains bad patterns.

    Root cause: a regex in date_patterns failed to compile, or a required
    profile key is missing.
    Remediation: validate profile JSON against the source_profile schema;
    check that all date_patterns are valid Python regex strings.
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(code="SOURCE_PROFILE", message=message, details=details)


class DateParseError(NewsParserError):
    """Raised when a date string cannot be parsed into a datetime.

    Root cause: the raw date string does not match any known date_pattern
    and is not a recognised relative timestamp.
    Remediation: add a matching date_pattern to the source profile or verify
    the raw string format. The unparseable value is stored in self.raw_value.
    """

    def __init__(self, message: str, raw_value: str | None = None):
        details = {"raw_value": raw_value} if raw_value is not None else None
        super().__init__(message=message, details=details)
        self.raw_value = raw_value


class SegmentationError(NewsParserError):
    """Raised when story segmentation produces incoherent blocks.

    Root cause: no date anchors found or heading/date alignment is impossible.
    Remediation: check that the page text contains date lines matching the
    source profile date_patterns; verify noise stripping did not remove anchors.
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message=message, details=details)


class DeduplicationError(NewsParserError):
    """Raised when deduplication logic encounters an unrecoverable state.

    Root cause: a malformed story dict is missing the 'headline' key needed
    for the dedup primary key.
    Remediation: ensure all story dicts emitted by segmentation contain at
    least a 'headline' field.
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message=message, details=details)
