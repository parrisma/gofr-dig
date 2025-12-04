"""Structure analysis for web pages.

This module provides functions to analyze the structure of HTML pages,
extracting semantic sections, navigation, and site organization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from app.logger import session_logger as logger


@dataclass
class PageSection:
    """Represents a semantic section of a page.

    Attributes:
        tag: HTML tag name (nav, header, main, article, etc.)
        id: Element ID if present
        classes: CSS classes
        heading: Section heading if present
        links_count: Number of links in this section
        text_preview: First 200 chars of text content
    """

    tag: str
    id: Optional[str] = None
    classes: List[str] = field(default_factory=list)
    heading: Optional[str] = None
    links_count: int = 0
    text_preview: str = ""


@dataclass
class LinkInfo:
    """Information about a link on the page.

    Attributes:
        url: Resolved URL
        text: Link text
        rel: rel attribute values
        type: Type of link (nav, content, footer, external)
        in_section: Which section the link appears in
    """

    url: str
    text: str
    rel: List[str] = field(default_factory=list)
    type: str = "content"
    in_section: Optional[str] = None


@dataclass
class PageStructure:
    """Structure analysis result for a page.

    Attributes:
        url: Page URL
        title: Page title
        language: Page language
        sections: List of semantic sections found
        navigation: Navigation links
        internal_links: Links to same domain
        external_links: Links to other domains
        meta: Page metadata
        forms: Form elements found
        outline: Document outline (headings hierarchy)
        error: Error message if analysis failed
    """

    url: str
    title: Optional[str] = None
    language: Optional[str] = None
    sections: List[Dict[str, Any]] = field(default_factory=list)
    navigation: List[Dict[str, str]] = field(default_factory=list)
    internal_links: List[Dict[str, str]] = field(default_factory=list)
    external_links: List[Dict[str, str]] = field(default_factory=list)
    meta: Dict[str, str] = field(default_factory=dict)
    forms: List[Dict[str, Any]] = field(default_factory=list)
    outline: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        """Check if analysis was successful."""
        return self.error is None


class StructureAnalyzer:
    """Analyze the structure of HTML pages.

    This class provides methods to extract structural information
    from HTML pages, including semantic sections, navigation,
    and document outline.

    Example:
        analyzer = StructureAnalyzer()
        structure = analyzer.analyze(html, url="https://example.com")
        print(structure.sections)
    """

    # Semantic section tags
    SECTION_TAGS = {"header", "nav", "main", "article", "section", "aside", "footer"}

    # Tags that typically contain navigation
    NAV_TAGS = {"nav"}
    NAV_CLASSES = {"nav", "navigation", "menu", "navbar", "header-nav", "main-nav"}
    NAV_IDS = {"nav", "navigation", "main-nav", "menu"}

    def __init__(self, parser: str = "html.parser"):
        """Initialize the structure analyzer.

        Args:
            parser: BeautifulSoup parser to use
        """
        self.parser = parser

    def analyze(self, html: str, url: str = "") -> PageStructure:
        """Analyze the structure of an HTML page.

        Args:
            html: HTML content to analyze
            url: Source URL for resolving relative links

        Returns:
            PageStructure with analysis results
        """
        try:
            soup = BeautifulSoup(html, self.parser)
        except Exception as e:
            logger.error("Failed to parse HTML for structure analysis", error=str(e))
            return PageStructure(url=url, error=f"Parse error: {str(e)}")

        # Extract basic info
        title = self._extract_title(soup)
        language = self._extract_language(soup)
        meta = self._extract_meta(soup)

        # Find semantic sections
        sections = self._find_sections(soup)

        # Extract navigation
        navigation = self._extract_navigation(soup, url)

        # Categorize all links
        internal_links, external_links = self._categorize_links(soup, url)

        # Find forms
        forms = self._find_forms(soup)

        # Build document outline
        outline = self._build_outline(soup)

        return PageStructure(
            url=url,
            title=title,
            language=language,
            sections=sections,
            navigation=navigation,
            internal_links=internal_links,
            external_links=external_links,
            meta=meta,
            forms=forms,
            outline=outline,
        )

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract page title."""
        title_tag = soup.find("title")
        if title_tag:
            return title_tag.get_text(strip=True)
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)
        return None

    def _extract_language(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract page language."""
        html_tag = soup.find("html")
        if html_tag and isinstance(html_tag, Tag):
            lang = html_tag.get("lang")
            if lang:
                return str(lang) if isinstance(lang, str) else str(lang[0])
        return None

    def _extract_meta(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Extract metadata from meta tags."""
        meta = {}
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

    def _find_sections(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Find semantic sections in the page."""
        sections = []

        for tag_name in self.SECTION_TAGS:
            for tag in soup.find_all(tag_name):
                if not isinstance(tag, Tag):
                    continue

                section = {
                    "tag": tag_name,
                    "id": tag.get("id"),
                    "classes": self._get_classes(tag),
                    "heading": self._find_section_heading(tag),
                    "links_count": len(tag.find_all("a")),
                    "text_preview": self._get_text_preview(tag),
                }
                sections.append(section)

        return sections

    def _get_classes(self, tag: Tag) -> List[str]:
        """Get CSS classes from a tag."""
        classes = tag.get("class")
        if classes is None:
            return []
        if isinstance(classes, str):
            return [classes]
        return list(classes)  # type: ignore[arg-type]

    def _find_section_heading(self, tag: Tag) -> Optional[str]:
        """Find the heading for a section."""
        for level in range(1, 7):
            heading = tag.find(f"h{level}")
            if heading:
                return heading.get_text(strip=True)
        return None

    def _get_text_preview(self, tag: Tag, max_length: int = 200) -> str:
        """Get a preview of the text content."""
        text = tag.get_text(separator=" ", strip=True)
        if len(text) > max_length:
            return text[:max_length] + "..."
        return text

    def _extract_navigation(
        self, soup: BeautifulSoup, base_url: str
    ) -> List[Dict[str, str]]:
        """Extract navigation links."""
        nav_links = []
        seen_urls = set()

        # Find nav elements
        nav_elements = soup.find_all("nav")

        # Also look for elements with nav-related classes/IDs
        for class_name in self.NAV_CLASSES:
            nav_elements.extend(soup.find_all(class_=class_name))
        for id_name in self.NAV_IDS:
            elem = soup.find(id=id_name)
            if elem:
                nav_elements.append(elem)

        # Extract links from nav elements
        for nav in nav_elements:
            for link in nav.find_all("a", href=True):
                href = link.get("href")
                if not href:
                    continue

                href_str = str(href) if isinstance(href, str) else str(href[0])

                if href_str.startswith("#") or href_str.startswith("javascript:"):
                    continue

                # Resolve URL
                if base_url:
                    resolved_url = urljoin(base_url, href_str)
                else:
                    resolved_url = href_str

                if resolved_url in seen_urls:
                    continue
                seen_urls.add(resolved_url)

                nav_links.append({
                    "url": resolved_url,
                    "text": link.get_text(strip=True),
                })

        return nav_links

    def _categorize_links(
        self, soup: BeautifulSoup, base_url: str
    ) -> tuple[List[Dict[str, str]], List[Dict[str, str]]]:
        """Categorize links as internal or external."""
        internal = []
        external = []
        seen_urls = set()

        base_domain = urlparse(base_url).netloc if base_url else ""

        for link in soup.find_all("a", href=True):
            href = link.get("href")
            if not href:
                continue

            href_str = str(href) if isinstance(href, str) else str(href[0])

            if href_str.startswith("#") or href_str.startswith("javascript:"):
                continue

            # Resolve URL
            if base_url:
                resolved_url = urljoin(base_url, href_str)
            else:
                resolved_url = href_str

            if resolved_url in seen_urls:
                continue
            seen_urls.add(resolved_url)

            link_info = {
                "url": resolved_url,
                "text": link.get_text(strip=True),
            }

            # Check if external
            link_domain = urlparse(resolved_url).netloc
            if link_domain and link_domain != base_domain:
                external.append(link_info)
            else:
                internal.append(link_info)

        return internal, external

    def _find_forms(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Find and analyze forms on the page."""
        forms = []

        for form in soup.find_all("form"):
            if not isinstance(form, Tag):
                continue

            method = form.get("method")
            form_info = {
                "id": form.get("id"),
                "action": form.get("action", ""),
                "method": (method.upper() if isinstance(method, str) else "GET"),
                "fields": [],
            }

            # Find input fields
            for inp in form.find_all(["input", "textarea", "select"]):
                if not isinstance(inp, Tag):
                    continue

                field = {
                    "type": inp.get("type", "text") if inp.name == "input" else inp.name,
                    "name": inp.get("name"),
                    "id": inp.get("id"),
                    "required": inp.get("required") is not None,
                }
                form_info["fields"].append(field)

            forms.append(form_info)

        return forms

    def _build_outline(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Build a document outline from headings."""
        outline = []

        for level in range(1, 7):
            for heading in soup.find_all(f"h{level}"):
                text = heading.get_text(strip=True)
                if text:
                    outline.append({
                        "level": level,
                        "text": text,
                        "id": heading.get("id"),
                    })

        return outline


# Global analyzer instance
_analyzer: Optional[StructureAnalyzer] = None


def get_analyzer() -> StructureAnalyzer:
    """Get the global structure analyzer instance."""
    global _analyzer
    if _analyzer is None:
        _analyzer = StructureAnalyzer()
    return _analyzer


def analyze_structure(html: str, url: str = "") -> PageStructure:
    """Convenience function to analyze page structure.

    Args:
        html: HTML content to analyze
        url: Source URL

    Returns:
        PageStructure with analysis results
    """
    analyzer = get_analyzer()
    return analyzer.analyze(html, url)
