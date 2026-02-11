"""Content extraction using BeautifulSoup.

This module provides functions to extract text content from HTML,
with support for CSS selectors and various extraction modes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from app.logger import session_logger as logger


@dataclass
class ExtractedContent:
    """Result of content extraction from HTML.

    Attributes:
        url: Source URL
        title: Page title
        text: Main text content
        headings: List of headings with their levels
        links: List of links found in the content
        images: List of images with alt text
        meta: Metadata from the page
        language: Detected or declared language
        error: Error message if extraction failed
    """

    url: str
    title: Optional[str] = None
    text: str = ""
    headings: List[Dict[str, str]] = field(default_factory=list)
    links: List[Dict[str, str]] = field(default_factory=list)
    images: List[Dict[str, str]] = field(default_factory=list)
    meta: Dict[str, str] = field(default_factory=dict)
    language: Optional[str] = None
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        """Check if extraction was successful."""
        return self.error is None


class ContentExtractor:
    """Extract content from HTML using BeautifulSoup.

    This class provides methods to extract various types of content
    from HTML pages, including text, links, images, and metadata.

    Example:
        extractor = ContentExtractor()
        content = extractor.extract(html, url="https://example.com")
        print(content.text)
    """

    # Tags to remove completely (including content)
    REMOVE_TAGS = {"script", "style", "noscript", "iframe", "svg", "canvas"}

    # Tags that typically contain the main content
    MAIN_CONTENT_TAGS = {"main", "article", "section", "div"}

    # CSS class/id patterns that indicate ad or noise elements
    AD_ELEMENT_PATTERNS = re.compile(
        r"(?i)"
        r"(?:^|[_-])(?:ad|ads|advert|advertisement|adslot|ad-slot|ad-container"
        r"|adsbygoogle|sponsored|sponsor|promo|promotion|banner-ad"
        r"|dfp|doubleclick|taboola|outbrain)"
        r"|(?:ad|ads|advert|advertisement|adslot|ad-slot|ad-container"
        r"|adsbygoogle|sponsored|sponsor|promo|promotion|banner-ad"
        r"|dfp|doubleclick|taboola|outbrain)(?:[_-]|$)"
    )

    # Text-level noise lines to strip (case-insensitive exact or near-exact matches)
    NOISE_LINE_PATTERNS = re.compile(
        r"^\s*(?:"
        # Ads & sponsorship
        r"advertisement|advertisements|advertise(?:ment)?s?"
        r"|sponsored\s*(?:content|post|links?)?"
        r"|ad|ads"
        r"|promoted\s*(?:content|stories)?"
        # Media labels / leaked icon names
        r"|multimedia|video|videos|slideshow|gallery|photo|photos"
        r"|play\s+video|watch\s+video"
        r"|videocam|photo_camera|play_arrow|play_circle"
        # Social / follow / share
        r"|\+?\s*follow(?:\s+us)?"
        r"|share(?:\s+this)?|tweet|email\s+this|print"
        # Read-more / load-more prompts
        r"|read\s+more|see\s+more|show\s+more|load\s+more|more\s+on\s+this"
        # Related / recommended
        r"|related\s+(?:stories|articles|topics|posts)"
        r"|you\s+may\s+also\s+like|recommended\s+for\s+you"
        # Comments
        r"|comments?|leave\s+a\s+comment|post\s+a\s+comment"
        # Cookie / consent
        r"|cookie\s+(?:policy|consent|settings|preferences)"
        r"|accept\s+(?:all\s+)?cookies?"
        r"|we\s+use\s+cookies"
        # Newsletter / subscribe
        r"|sign\s+up\s+(?:for|to)\s+(?:our\s+)?newsletter"
        r"|subscribe\s+(?:now|today|for\s+free)"
        # Skip-nav
        r"|skip\s+(?:to\s+)?(?:content|main|navigation)"
        # Standalone punctuation / decoration
        r"|[-–—|•·]{1,3}"
        r")\s*$",
        re.IGNORECASE,
    )

    # Semantic selectors for main content
    MAIN_CONTENT_SELECTORS = [
        "main",
        "article",
        "[role='main']",
        "#content",
        "#main-content",
        ".content",
        ".main-content",
        ".post-content",
        ".article-content",
    ]

    def __init__(self, parser: str = "html.parser"):
        """Initialize the content extractor.

        Args:
            parser: BeautifulSoup parser to use
        """
        self.parser = parser

    def extract(
        self,
        html: str,
        url: str = "",
        selector: Optional[str] = None,
        include_links: bool = True,
        include_images: bool = True,
        include_meta: bool = True,
        filter_noise: bool = False,
    ) -> ExtractedContent:
        """Extract content from HTML.

        Args:
            html: HTML content to parse
            url: Source URL for resolving relative links
            selector: Optional CSS selector to limit extraction scope
            include_links: Whether to extract links
            include_images: Whether to extract images
            include_meta: Whether to extract metadata

        Returns:
            ExtractedContent with extracted data
        """
        try:
            soup = BeautifulSoup(html, self.parser)
        except Exception as e:
            logger.error("Failed to parse HTML", error=str(e))
            return ExtractedContent(url=url, error=f"Parse error: {str(e)}")

        # Remove unwanted tags
        for tag in soup.find_all(self.REMOVE_TAGS):
            tag.decompose()

        # Remove ad/noise elements when filtering is enabled
        if filter_noise:
            self._remove_ad_elements(soup)

        # Get the scope for extraction
        scope = soup
        if selector:
            scope = soup.select_one(selector)
            if scope is None:
                return ExtractedContent(
                    url=url,
                    error=f"Selector '{selector}' did not match any elements",
                )

        # Extract language
        language = self._extract_language(soup)

        # Extract title
        title = self._extract_title(soup)

        # Extract metadata
        meta = self._extract_meta(soup) if include_meta else {}

        # Extract main text
        text = self._extract_text(scope)

        # Apply text-level noise filtering
        if filter_noise:
            text = self._filter_noise_text(text)

        # Extract headings
        headings = self._extract_headings(scope)

        # Extract links
        links = self._extract_links(scope, url) if include_links else []

        # Extract images
        images = self._extract_images(scope, url) if include_images else []

        return ExtractedContent(
            url=url,
            title=title,
            text=text,
            headings=headings,
            links=links,
            images=images,
            meta=meta,
            language=language,
        )

    def _extract_language(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract language from HTML element or meta tag."""
        html_tag = soup.find("html")
        if html_tag and isinstance(html_tag, Tag):
            lang = html_tag.get("lang")
            if lang:
                return str(lang) if isinstance(lang, str) else str(lang[0])

        # Try meta tag
        meta = soup.find("meta", attrs={"http-equiv": "Content-Language"})
        if meta and isinstance(meta, Tag):
            content = meta.get("content")
            if content:
                return str(content) if isinstance(content, str) else str(content[0])

        return None

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract page title."""
        title_tag = soup.find("title")
        if title_tag:
            return title_tag.get_text(strip=True)

        # Try h1 as fallback
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)

        return None

    def _extract_meta(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Extract metadata from meta tags."""
        meta = {}

        # Standard meta tags
        for tag in soup.find_all("meta"):
            if not isinstance(tag, Tag):
                continue

            name = tag.get("name") or tag.get("property")
            content = tag.get("content")

            if name and content:
                name_str = str(name) if isinstance(name, str) else str(name[0])
                content_str = str(content) if isinstance(content, str) else str(content[0])
                meta[name_str] = content_str

        return meta

    def _remove_ad_elements(self, soup: BeautifulSoup) -> None:
        """Remove HTML elements that look like ads or noise.

        Inspects class and id attributes for common ad-related patterns.
        """
        to_remove = []
        for tag in soup.find_all(True):
            # Skip tags already decomposed (attrs becomes None)
            if not hasattr(tag, "attrs") or tag.attrs is None:
                continue
            cls = tag.get("class")
            classes = " ".join(cls) if isinstance(cls, list) else (str(cls) if cls else "")
            tag_id = tag.get("id") or ""
            combined = f"{classes} {tag_id}"
            if combined.strip() and self.AD_ELEMENT_PATTERNS.search(combined):
                to_remove.append(tag)
        for tag in to_remove:
            tag.decompose()
        if to_remove:
            logger.debug("Removed ad/noise elements", count=len(to_remove))

    def _filter_noise_text(self, text: str) -> str:
        """Remove noise lines from extracted text.

        Strips lines that match common advertisement / cookie-banner
        patterns and collapses resulting blank-line runs.
        """
        lines = text.split("\n")
        filtered = [line for line in lines if not self.NOISE_LINE_PATTERNS.match(line)]
        result = "\n".join(filtered)
        # Collapse triple+ newlines that may result from removal
        result = re.sub(r"\n{3,}", "\n\n", result)
        return result.strip()

    def _extract_text(self, element) -> str:
        """Extract clean text from an element.

        Uses a custom algorithm to preserve some structure while
        removing excessive whitespace.
        """
        if element is None:
            return ""

        # Get text with separator
        text = element.get_text(separator="\n", strip=True)

        # Clean up excessive newlines
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Clean up excessive spaces
        text = re.sub(r"[ \t]+", " ", text)

        return text.strip()

    def _extract_headings(self, element) -> List[Dict[str, str]]:
        """Extract headings with their levels."""
        headings = []

        for level in range(1, 7):
            for tag in element.find_all(f"h{level}"):
                text = tag.get_text(strip=True)
                if text:
                    headings.append({"level": level, "text": text})

        return headings

    def _extract_links(self, element, base_url: str) -> List[Dict[str, str]]:
        """Extract links with text and resolved URLs."""
        links = []
        seen_urls = set()

        for tag in element.find_all("a", href=True):
            href = tag.get("href")
            if not href:
                continue

            # Get href as string
            href_str = str(href) if isinstance(href, str) else str(href[0])

            # Skip anchors and javascript
            if href_str.startswith("#") or href_str.startswith("javascript:"):
                continue

            # Resolve relative URLs
            if base_url:
                resolved_url = urljoin(base_url, href_str)
            else:
                resolved_url = href_str

            # Skip duplicates
            if resolved_url in seen_urls:
                continue
            seen_urls.add(resolved_url)

            text = tag.get_text(strip=True)
            title = tag.get("title", "")
            if isinstance(title, list):
                title = title[0] if title else ""

            # Determine if external
            is_external = False
            if base_url:
                base_domain = urlparse(base_url).netloc
                link_domain = urlparse(resolved_url).netloc
                is_external = link_domain != base_domain and bool(link_domain)

            links.append(
                {
                    "url": resolved_url,
                    "text": text,
                    "title": str(title),
                    "external": is_external,
                }
            )

        return links

    def _extract_images(self, element, base_url: str) -> List[Dict[str, str]]:
        """Extract images with alt text and resolved URLs."""
        images = []

        for tag in element.find_all("img", src=True):
            src = tag.get("src")
            if not src:
                continue

            # Get src as string
            src_str = str(src) if isinstance(src, str) else str(src[0])

            # Resolve relative URLs
            if base_url:
                resolved_url = urljoin(base_url, src_str)
            else:
                resolved_url = src_str

            alt = tag.get("alt", "")
            if isinstance(alt, list):
                alt = alt[0] if alt else ""

            images.append({"url": resolved_url, "alt": str(alt)})

        return images

    def extract_by_selector(
        self,
        html: str,
        selector: str,
        url: str = "",
        filter_noise: bool = False,
    ) -> ExtractedContent:
        """Extract content from elements matching a CSS selector.

        Args:
            html: HTML content to parse
            selector: CSS selector
            url: Source URL

        Returns:
            ExtractedContent with text from all matching elements
        """
        try:
            soup = BeautifulSoup(html, self.parser)
        except Exception as e:
            logger.error("Failed to parse HTML for selector extraction", error=str(e), selector=selector)
            return ExtractedContent(url=url, error=f"Parse error: {str(e)}")

        # Remove ad/noise elements when filtering is enabled
        if filter_noise:
            self._remove_ad_elements(soup)

        try:
            elements = soup.select(selector)
        except Exception as e:
            logger.warning("Invalid CSS selector", selector=selector, error=str(e))
            return ExtractedContent(
                url=url,
                error=f"Invalid selector '{selector}': {str(e)}",
            )

        if not elements:
            return ExtractedContent(
                url=url,
                error=f"Selector '{selector}' did not match any elements",
            )

        # Combine text from all matching elements
        texts = []
        for elem in elements:
            text = self._extract_text(elem)
            if text:
                texts.append(text)

        combined_text = "\n\n".join(texts)
        if filter_noise:
            combined_text = self._filter_noise_text(combined_text)

        return ExtractedContent(
            url=url,
            title=self._extract_title(soup),
            text=combined_text,
            language=self._extract_language(soup),
        )

    def extract_main_content(
        self, html: str, url: str = "", filter_noise: bool = False,
    ) -> ExtractedContent:
        """Extract the main content area of a page.

        Tries various common selectors to find the main content.

        Args:
            html: HTML content to parse
            url: Source URL

        Returns:
            ExtractedContent with main content text
        """
        try:
            soup = BeautifulSoup(html, self.parser)
        except Exception as e:
            logger.error("Failed to parse HTML for main content extraction", error=str(e), url=url)
            return ExtractedContent(url=url, error=f"Parse error: {str(e)}")

        # Remove unwanted tags first
        for tag in soup.find_all(self.REMOVE_TAGS):
            tag.decompose()

        # Remove ad/noise elements when filtering is enabled
        if filter_noise:
            self._remove_ad_elements(soup)

        # Try to find main content area
        main_element = None
        for selector in self.MAIN_CONTENT_SELECTORS:
            main_element = soup.select_one(selector)
            if main_element:
                logger.debug("Found main content", selector=selector)
                break

        # Fall back to body
        if main_element is None:
            main_element = soup.find("body") or soup

        text = self._extract_text(main_element)
        if filter_noise:
            text = self._filter_noise_text(text)

        return ExtractedContent(
            url=url,
            title=self._extract_title(soup),
            text=text,
            headings=self._extract_headings(main_element),
            links=self._extract_links(main_element, url),
            images=self._extract_images(main_element, url),
            meta=self._extract_meta(soup),
            language=self._extract_language(soup),
        )


# Global extractor instance
_extractor: Optional[ContentExtractor] = None


def get_extractor() -> ContentExtractor:
    """Get the global content extractor instance."""
    global _extractor
    if _extractor is None:
        _extractor = ContentExtractor()
    return _extractor


def extract_content(
    html: str,
    url: str = "",
    selector: Optional[str] = None,
    filter_noise: bool = False,
) -> ExtractedContent:
    """Convenience function to extract content from HTML.

    Args:
        html: HTML content to parse
        url: Source URL
        selector: Optional CSS selector
        filter_noise: Strip ad/noise elements and text lines

    Returns:
        ExtractedContent with extracted data
    """
    extractor = get_extractor()
    if selector:
        return extractor.extract_by_selector(html, selector, url, filter_noise=filter_noise)
    return extractor.extract_main_content(html, url, filter_noise=filter_noise)
