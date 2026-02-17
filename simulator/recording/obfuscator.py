"""Content obfuscation engine for the simulator recorder.

Transforms live HTML into copyright-safe, PII-free fixtures that preserve
DOM structure, class names, IDs, and element hierarchy so that CSS selectors
and extraction logic continue to work against the recorded content.

Three scrubbing passes:
  1. scrub_pii   — regex-based redaction of emails, phone numbers.
  2. scrub_text  — replace visible text nodes with length-matched lorem ipsum.
  3. scrub_media — replace <img> src/srcset with SVG placeholders.

The combined entry point is ``obfuscate(html)``.
"""

from __future__ import annotations

import hashlib
import re
from html.parser import HTMLParser
from io import StringIO

# ---------------------------------------------------------------------------
# Lorem ipsum word pool (used for length-matched text replacement)
# ---------------------------------------------------------------------------

_LOREM_WORDS = (
    "lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod "
    "tempor incididunt ut labore et dolore magna aliqua enim ad minim veniam "
    "quis nostrud exercitation ullamco laboris nisi aliquip ex ea commodo "
    "consequat duis aute irure in reprehenderit voluptate velit esse cillum "
    "fugiat nulla pariatur excepteur sint occaecat cupidatat non proident "
    "sunt culpa qui officia deserunt mollit anim id est laborum"
).split()

# ---------------------------------------------------------------------------
# PII patterns
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
)

_PHONE_RE = re.compile(
    r"""
    (?<!\d)                               # not preceded by digit
    (?:
        \+?\d{1,3}[\s\-.]?               # optional country code
    )?
    (?:
        \(?\d{2,4}\)?[\s\-.]?            # area code
    )
    \d{3,4}[\s\-.]?\d{3,4}              # subscriber number
    (?!\d)                                # not followed by digit
    """,
    re.VERBOSE,
)

# ---------------------------------------------------------------------------
# Placeholder SVG for images
# ---------------------------------------------------------------------------

_PLACEHOLDER_SVG = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' "
    "width='400' height='300'%3E%3Crect width='100%25' height='100%25' "
    "fill='%23ddd'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' "
    "text-anchor='middle' fill='%23999' font-size='18'%3E"
    "placeholder%3C/text%3E%3C/svg%3E"
)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def obfuscate(html: str) -> str:
    """Full obfuscation pipeline: PII → text → media.

    Returns valid HTML with the same DOM structure but all human-readable
    content replaced.
    """
    result = scrub_pii(html)
    result = scrub_text(result)
    result = scrub_media(result)
    return result


def scrub_pii(text: str) -> str:
    """Replace email addresses and phone numbers with redacted placeholders."""
    result = _EMAIL_RE.sub(_redact_email, text)
    result = _PHONE_RE.sub(_redact_phone, result)
    return result


def scrub_text(html: str) -> str:
    """Replace visible text nodes with length-matched lorem ipsum.

    Preserves:
      - All tags, attributes, classes, IDs
      - Whitespace-only text nodes
      - Text inside <script>, <style>, <code>, <pre> elements
    """
    parser = _TextScrubber()
    parser.feed(html)
    return parser.get_output()


def scrub_media(html: str) -> str:
    """Replace <img> src and srcset attributes with SVG placeholders."""
    result = _IMG_SRC_RE.sub(_replace_img_src, html)
    result = _IMG_SRCSET_RE.sub(_replace_img_srcset, result)
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _redact_email(match: re.Match) -> str:
    """Replace email with same-length redacted version."""
    original = match.group(0)
    return "x" * len(original)


def _redact_phone(match: re.Match) -> str:
    """Replace phone with same-length redacted version."""
    original = match.group(0)
    # Preserve formatting chars, replace digits
    return "".join("0" if c.isdigit() else c for c in original)


def _lorem_for_length(length: int, seed: str = "") -> str:
    """Generate lorem ipsum text of approximately the given character length.

    Uses a deterministic seed so the same input always produces the same output.
    """
    if length <= 0:
        return ""

    # Seed the word selection for determinism
    h = int(hashlib.md5(seed.encode(), usedforsecurity=False).hexdigest()[:8], 16)
    pool = _LOREM_WORDS
    pool_len = len(pool)

    words: list[str] = []
    char_count = 0
    idx = h % pool_len

    while char_count < length:
        word = pool[idx % pool_len]
        if char_count + len(word) + (1 if words else 0) > length + 5:
            # Close enough — avoid excessive overshoot
            break
        if words:
            char_count += 1  # space
        words.append(word)
        char_count += len(word)
        idx += 1

    result = " ".join(words)

    # Trim or pad to hit the target more closely
    if len(result) > length:
        result = result[:length].rstrip()
    elif len(result) < length:
        result = result + " " * (length - len(result))

    return result


# Tags whose text content should NOT be replaced
_PRESERVE_TEXT_TAGS = frozenset({
    "script", "style", "code", "pre", "textarea",
    "noscript", "template",
})

# Whitespace-only pattern
_WS_ONLY = re.compile(r"^\s*$")


class _TextScrubber(HTMLParser):
    """HTML parser that replaces text nodes with lorem ipsum."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._output = StringIO()
        self._tag_stack: list[str] = []

    def get_output(self) -> str:
        return self._output.getvalue()

    def _in_preserved_tag(self) -> bool:
        return any(t in _PRESERVE_TEXT_TAGS for t in self._tag_stack)

    # -- Parser callbacks --

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._tag_stack.append(tag.lower())
        attr_str = _format_attrs(attrs)
        self._output.write(f"<{tag}{attr_str}>")

    def handle_endtag(self, tag: str) -> None:
        # Pop matching tag (tolerant of mismatches in real-world HTML)
        tag_lower = tag.lower()
        if self._tag_stack and self._tag_stack[-1] == tag_lower:
            self._tag_stack.pop()
        elif tag_lower in self._tag_stack:
            # Unwind to the matching tag
            while self._tag_stack and self._tag_stack[-1] != tag_lower:
                self._tag_stack.pop()
            if self._tag_stack:
                self._tag_stack.pop()
        self._output.write(f"</{tag}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_str = _format_attrs(attrs)
        self._output.write(f"<{tag}{attr_str} />")

    def handle_data(self, data: str) -> None:
        if self._in_preserved_tag() or _WS_ONLY.match(data):
            self._output.write(data)
        else:
            self._output.write(_lorem_for_length(len(data), seed=data))

    def handle_entityref(self, name: str) -> None:
        self._output.write(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self._output.write(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        self._output.write(f"<!--{data}-->")

    def handle_decl(self, decl: str) -> None:
        self._output.write(f"<!{decl}>")

    def handle_pi(self, data: str) -> None:
        self._output.write(f"<?{data}>")

    def unknown_decl(self, data: str) -> None:
        self._output.write(f"<![{data}]>")


def _format_attrs(attrs: list[tuple[str, str | None]]) -> str:
    """Format attribute list back to HTML string."""
    if not attrs:
        return ""
    parts: list[str] = []
    for name, value in attrs:
        if value is None:
            parts.append(f" {name}")
        else:
            # Use double quotes, escape embedded quotes
            escaped = value.replace("&", "&amp;").replace('"', "&quot;")
            parts.append(f' {name}="{escaped}"')
    return "".join(parts)


# ---------------------------------------------------------------------------
# Media replacement regexes
# ---------------------------------------------------------------------------

_IMG_SRC_RE = re.compile(
    r"(<img\b[^>]*?\bsrc\s*=\s*)(\"[^\"]*\"|'[^']*')",
    re.IGNORECASE | re.DOTALL,
)

_IMG_SRCSET_RE = re.compile(
    r"(<img\b[^>]*?\bsrcset\s*=\s*)(\"[^\"]*\"|'[^']*')",
    re.IGNORECASE | re.DOTALL,
)


def _replace_img_src(match: re.Match) -> str:
    prefix = match.group(1)
    return f'{prefix}"{_PLACEHOLDER_SVG}"'


def _replace_img_srcset(match: re.Match) -> str:
    prefix = match.group(1)
    return f'{prefix}"{_PLACEHOLDER_SVG}"'
