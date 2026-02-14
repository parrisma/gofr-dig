"""Deterministic news parser for gofr-dig crawl output.

Transforms raw crawl results into a structured feed suitable for downstream LLM
analysis without introducing summarization or external calls.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from app.exceptions import (
    CrawlInputError,
    DateParseError,
    DeduplicationError,
    SourceProfileError,
)
from app.logger import session_logger as logger
from app.processing.source_profiles import get_source_profile


_DATE_FMT = "%d %b %Y - %I:%M%p"
_RELATIVE_RE = re.compile(r"(?P<count>\d+)\s+(?P<unit>minutes?|hours?|days?)\s+ago", re.IGNORECASE)
_DURATION_RE = re.compile(r"^\d{2}:\d{2}$")
_COMMENT_COUNT_RE = re.compile(r"^\d+$")
_PIPE_SPLIT_RE = re.compile(r"^\s*([^|]{1,64})\|(.+)$")
_AUTHOR_RE = re.compile(r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}$")


class NewsParser:
    """Post-processing parser for crawl output.

    Main entry accepts a get_content result dict and returns a deterministic feed.
    """

    def parse(self, crawl_result: dict) -> dict:
        """Main entry — takes raw get_content result dict, returns feed dict."""
        self._validate_input(crawl_result)

        crawl_time = self._parse_crawl_time(crawl_result.get("crawl_time_utc"))
        parser_version = crawl_result.get("parser_version") or "1.0.0"
        source_profile = self._resolve_source_profile(crawl_result)
        start_url = crawl_result["start_url"]

        stories_raw: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        noise_total = 0

        pages = crawl_result.get("pages", [])
        for page in pages:
            text = page.get("text") or ""
            cleaned_text, lines_removed, strip_warnings = self._strip_noise(text, source_profile)
            noise_total += lines_removed
            warnings.extend(strip_warnings)

            page_stories = self._segment_stories(
                cleaned_text=cleaned_text,
                headings=page.get("headings", []),
                meta=page.get("meta", {}),
                source_profile=source_profile,
                crawl_time=crawl_time,
                page=page,
                start_url=start_url,
                warnings=warnings,
            )
            stories_raw.extend(page_stories)

        unique_stories, duplicates_removed = self._deduplicate(stories_raw)

        for story in unique_stories:
            story["parse_quality"] = self._compute_parse_quality(story)

        feed_meta = {
            "parser_version": parser_version,
            "source_profile": source_profile["name"],
            "source_name": source_profile.get("display_name") or source_profile["name"],
            "source_root_url": start_url,
            "crawl_time_utc": crawl_time.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "pages_crawled": len(pages),
            "stories_extracted": len(unique_stories),
            "duplicates_removed": duplicates_removed,
            "noise_lines_stripped": noise_total,
            "parse_warnings": len(warnings),
        }

        output = {
            "feed_meta": feed_meta,
            "stories": unique_stories,
        }
        if warnings:
            output["warnings"] = warnings

        logger.info(
            "news_parser_completed",
            pages_crawled=len(pages),
            stories_extracted=len(unique_stories),
            duplicates_removed=duplicates_removed,
            noise_lines_stripped=noise_total,
            parse_warnings=len(warnings),
            source_profile=source_profile["name"],
        )
        return output

    def _validate_input(self, crawl_result: dict) -> None:
        if not isinstance(crawl_result, dict):
            raise CrawlInputError("crawl_result must be a dict")
        if "start_url" not in crawl_result:
            raise CrawlInputError("crawl_result missing required key: start_url")
        if "pages" not in crawl_result or not isinstance(crawl_result["pages"], list):
            raise CrawlInputError("crawl_result missing required key: pages (list)")

    def _parse_crawl_time(self, crawl_time_raw: str | None) -> datetime:
        if not crawl_time_raw:
            return datetime.now(timezone.utc)
        try:
            if crawl_time_raw.endswith("Z"):
                crawl_time_raw = crawl_time_raw[:-1] + "+00:00"
            parsed = datetime.fromisoformat(crawl_time_raw)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError as exc:
            raise CrawlInputError(
                "crawl_time_utc must be a valid ISO-8601 datetime string"
            ) from exc

    def _resolve_source_profile(self, crawl_result: dict) -> dict:
        """Returns source profile configuration used by parser."""
        profile_name = crawl_result.get("source_profile_name")
        profile = get_source_profile(profile_name)

        required_keys = {
            "name",
            "timezone",
            "utc_offset",
            "date_patterns",
            "section_labels",
            "noise_markers",
            "sponsored_markers",
            "exclusive_markers",
            "opinion_labels",
        }
        missing = [key for key in required_keys if key not in profile]
        if missing:
            raise SourceProfileError(f"source profile missing required keys: {missing}")

        for pattern in profile.get("date_patterns", []):
            try:
                re.compile(pattern)
            except re.error as exc:
                raise SourceProfileError(
                    f"invalid date regex pattern in source profile: {pattern}"
                ) from exc

        return profile

    def _strip_noise(self, text: str, source_profile: dict) -> tuple[str, int, list[dict[str, Any]]]:
        """Returns (cleaned_text, lines_removed, warnings)."""
        lines = [line.rstrip() for line in text.splitlines()]
        cleaned: list[str] = []
        removed = 0
        warnings: list[dict[str, Any]] = []

        noise_markers = set(source_profile.get("noise_markers", []))

        date_re = self._compile_date_regex(source_profile)

        for idx, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                cleaned.append(line)
                continue

            looks_like_noise = False
            if stripped in noise_markers:
                looks_like_noise = True
            elif stripped.startswith("Photo:") or stripped.startswith("Illustration:"):
                looks_like_noise = True
            elif _DURATION_RE.match(stripped):
                looks_like_noise = True
            elif "sentry-trace" in stripped.lower() or "baggage" in stripped.lower() or "appstore" in stripped.lower():
                looks_like_noise = True

            if looks_like_noise:
                # Safety rule: keep if line likely contains a story anchor context
                prev_line = lines[idx - 1].strip() if idx > 0 else ""
                next_line = lines[idx + 1].strip() if idx + 1 < len(lines) else ""
                if date_re.search(prev_line) or date_re.search(next_line):
                    warnings.append(
                        {
                            "code": "STRIP_RULE_SKIPPED_STORY_SAFETY",
                            "example": stripped[:120],
                        }
                    )
                    cleaned.append(line)
                else:
                    removed += 1
                continue

            cleaned.append(line)

        return "\n".join(cleaned), removed, warnings

    def _segment_stories(
        self,
        cleaned_text: str,
        headings: list,
        meta: dict,
        source_profile: dict,
        crawl_time: datetime,
        page: dict,
        start_url: str,
        warnings: list[dict[str, Any]],
    ) -> list[dict]:
        """Returns list of raw story dicts."""
        lines = [line.strip() for line in cleaned_text.splitlines()]
        lines = [line for line in lines if line]
        if not lines:
            return []

        date_re = self._compile_date_regex(source_profile)
        date_indices = [idx for idx, line in enumerate(lines) if date_re.search(line)]
        if not date_indices:
            return []

        stories: list[dict[str, Any]] = []

        for i, date_idx in enumerate(date_indices):
            block_start = date_indices[i - 1] + 1 if i > 0 else 0
            block_end = date_indices[i + 1] if i + 1 < len(date_indices) else len(lines)
            block = lines[block_start:block_end]
            if not block:
                continue

            story = self._story_from_block(
                block=block,
                source_profile=source_profile,
                crawl_time=crawl_time,
                page=page,
                start_url=start_url,
                headings=headings,
                meta=meta,
                warnings=warnings,
            )
            if story:
                stories.append(story)

        return stories

    def _story_from_block(
        self,
        block: list[str],
        source_profile: dict,
        crawl_time: datetime,
        page: dict,
        start_url: str,
        headings: list,
        meta: dict,
        warnings: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        date_re = self._compile_date_regex(source_profile)

        date_idx = None
        for idx, line in enumerate(block):
            if date_re.search(line):
                date_idx = idx
                break

        if date_idx is None:
            return None

        published_raw = block[date_idx]
        pre = block[:date_idx]
        post = block[date_idx + 1 :]

        section_labels = set(source_profile.get("section_labels", []))

        section: str | None = None
        headline: str | None = None
        subheadline: str | None = None
        segmentation_reason = "date_anchor+heading_alignment"
        opinion_labels = set(source_profile.get("opinion_labels", []))

        if pre:
            exclusive_markers = set(source_profile.get("exclusive_markers", []))
            sponsored_markers = set(source_profile.get("sponsored_markers", []))
            pre = [
                line
                for line in pre
                if line not in exclusive_markers and line not in sponsored_markers
            ]

        if pre:
            section_index = 0
            while section_index < len(pre) and pre[section_index] in section_labels:
                section = pre[section_index]
                section_index += 1

            remainder = pre[section_index:]

            if remainder:
                pipe_line = next((line for line in remainder if "|" in line), None)
                if pipe_line is not None:
                    headline = pipe_line
                    pipe_idx = remainder.index(pipe_line)
                    if not section and pipe_idx > 0 and remainder[pipe_idx - 1] in opinion_labels:
                        section = remainder[pipe_idx - 1]
                    if pipe_idx + 1 < len(remainder):
                        candidate_subheadline = remainder[pipe_idx + 1]
                        if (
                            candidate_subheadline not in opinion_labels
                            and not _AUTHOR_RE.match(candidate_subheadline)
                        ):
                            subheadline = candidate_subheadline
                else:
                    headline = remainder[0]
                    if len(remainder) > 1:
                        candidate_subheadline = remainder[1]
                        if (
                            candidate_subheadline not in opinion_labels
                            and not _AUTHOR_RE.match(candidate_subheadline)
                        ):
                            subheadline = candidate_subheadline

        if not headline:
            segmentation_reason = "date_anchor+nearest_preceding_line_fallback"
            headline = self._fallback_headline(block, date_idx)
            if not headline:
                warnings.append(
                    {
                        "code": "STORY_SKIPPED_NO_HEADLINE",
                        "example": published_raw[:120],
                    }
                )
                return None

        headline, pipe_section = self._handle_pipe_headline(headline)
        if not section and pipe_section:
            section = pipe_section

        comment_count = None
        if post and _COMMENT_COUNT_RE.match(post[-1]):
            try:
                comment_count = int(post[-1])
            except ValueError:
                comment_count = None

        body_lines = [line for line in post if not _COMMENT_COUNT_RE.match(line)]
        body_snippet = " ".join(body_lines[:4]).strip() or None
        if body_snippet and len(body_snippet) > 400:
            body_snippet = body_snippet[:400].rstrip() + "..."

        try:
            published = self._normalise_date(
                raw=published_raw,
                crawl_time=crawl_time,
                profile=source_profile,
            )
        except DateParseError:
            published = None
            warnings.append(
                {
                    "code": "DATE_PARSE_FAILED",
                    "example": published_raw[:120],
                }
            )

        language = page.get("language") or meta.get("language")

        story: dict[str, Any] = {
            "story_id": self._story_id(
                source_profile=source_profile,
                headline=headline,
                published=published,
                page_url=page.get("url", ""),
            ),
            "headline": headline,
            "subheadline": subheadline,
            "section": section,
            "published": published,
            "published_raw": published_raw,
            "body_snippet": body_snippet,
            "comment_count": comment_count,
            "tags": [],
            "content_type": "news",
            "author": None,
            "provenance": self._build_provenance(page, start_url),
            "seen_on_pages": [
                {
                    "page_url": page.get("url"),
                    "crawl_depth": page.get("depth"),
                }
            ],
            "language": language,
            "_segmentation_reason": segmentation_reason,
            "_raw_block": block,
        }

        story["content_type"], story_tags = self._classify(story, source_profile)
        story["tags"] = story_tags

        if story["content_type"] == "opinion":
            story["author"] = self._extract_opinion_author(block, source_profile)

        return story

    def _normalise_date(self, raw: str, crawl_time: datetime, profile: dict) -> str | None:
        """Returns ISO 8601 string."""
        raw_s = raw.strip()

        # Relative timestamps
        rel_match = _RELATIVE_RE.search(raw_s)
        if rel_match:
            count = int(rel_match.group("count"))
            unit = rel_match.group("unit").lower()
            if "minute" in unit:
                dt = crawl_time - timedelta(minutes=count)
            elif "hour" in unit:
                dt = crawl_time - timedelta(hours=count)
            else:
                dt = crawl_time - timedelta(days=count)
            return dt.isoformat()

        # Explicit pattern like "13 Feb 2026 - 10:15PM"
        try:
            parsed = datetime.strptime(raw_s, _DATE_FMT)
            offset = profile.get("utc_offset", "+00:00")
            sign = 1 if offset.startswith("+") else -1
            hh, mm = offset[1:].split(":")
            tz = timezone(sign * timedelta(hours=int(hh), minutes=int(mm)))
            return parsed.replace(tzinfo=tz).isoformat()
        except ValueError:
            pass

        raise DateParseError(
            "date string could not be parsed with configured patterns",
            raw_value=raw,
        )

    def _deduplicate(self, stories: list[dict]) -> tuple[list[dict], int]:
        """Returns (unique_stories, duplicates_removed)."""
        by_key: dict[tuple, dict[str, Any]] = {}
        duplicates_removed = 0

        for story in stories:
            if "headline" not in story or not story["headline"]:
                raise DeduplicationError("story missing headline in deduplication phase")

            key = self._dedupe_key(story)
            existing = by_key.get(key)
            if not existing:
                by_key[key] = story
                continue

            winner = self._pick_richer_story(existing, story)
            loser = story if winner is existing else existing

            winner_seen = winner.setdefault("seen_on_pages", [])
            loser_seen = loser.get("seen_on_pages", [])
            winner_seen.extend(loser_seen)

            by_key[key] = winner
            duplicates_removed += 1

        unique = list(by_key.values())
        unique.sort(key=lambda item: item.get("published") or "", reverse=True)
        return unique, duplicates_removed

    def _classify(self, story: dict, source_profile: dict) -> tuple[str, list[str]]:
        """Returns content_type and tags list."""
        tags: list[str] = []

        block = story.get("_raw_block", [])
        headline = (story.get("headline") or "").strip()
        subheadline = (story.get("subheadline") or "").strip()
        section = (story.get("section") or "").strip()

        exclusive_markers = set(source_profile.get("exclusive_markers", []))
        sponsored_markers = set(source_profile.get("sponsored_markers", []))
        opinion_labels = set(source_profile.get("opinion_labels", []))

        if any(marker in block for marker in exclusive_markers):
            tags.append("exclusive")

        if any(marker in block for marker in sponsored_markers):
            return "sponsored", tags

        if section in opinion_labels or headline.startswith("Opinion|"):
            return "opinion", tags

        joined = f"{headline} {subheadline}".lower()
        if any(token in joined for token in ["analysis", "deep dive", "explainer"]):
            return "analysis", tags

        if block and any(_DURATION_RE.match(line) for line in block[:2]):
            return "video", tags

        return "news", tags

    def _build_provenance(self, page: dict, start_url: str) -> dict:
        """Returns provenance dict for a story."""
        return {
            "root_url": start_url,
            "page_url": page.get("url"),
            "crawl_depth": page.get("depth"),
        }

    def _compute_parse_quality(self, story: dict) -> dict:
        """Returns parse quality payload for a story."""
        missing_fields: list[str] = []
        for field in ["headline", "section", "subheadline", "published"]:
            value = story.get(field)
            if value is None or value == "":
                missing_fields.append(field)

        confidence = 1.0
        confidence -= 0.12 * len(missing_fields)

        if story.get("_segmentation_reason") == "date_anchor+nearest_preceding_line_fallback":
            confidence -= 0.15

        if story.get("published") is None and story.get("published_raw"):
            confidence -= 0.1

        confidence = max(0.0, min(1.0, round(confidence, 2)))

        return {
            "parse_confidence": confidence,
            "missing_fields": missing_fields,
            "segmentation_reason": story.get("_segmentation_reason")
            or "date_anchor+heading_alignment",
        }

    def _compile_date_regex(self, source_profile: dict) -> re.Pattern:
        patterns = source_profile.get("date_patterns", [])
        if not patterns:
            raise SourceProfileError("source profile date_patterns cannot be empty")
        return re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE)

    def _fallback_headline(self, block: list[str], date_idx: int) -> str | None:
        for idx in range(date_idx - 1, -1, -1):
            candidate = block[idx].strip()
            if candidate:
                return candidate
        return None

    def _handle_pipe_headline(self, headline: str) -> tuple[str, str | None]:
        match = _PIPE_SPLIT_RE.match(headline)
        if not match:
            return headline.strip(), None
        section = match.group(1).strip()
        cleaned = match.group(2).strip()
        return cleaned, section

    def _story_id(
        self,
        source_profile: dict,
        headline: str,
        published: str | None,
        page_url: str,
    ) -> str:
        raw = "|".join([source_profile["name"], headline.lower(), published or "", page_url])
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
        return f"{source_profile['name']}:{digest}"

    def _dedupe_key(self, story: dict) -> tuple:
        headline_norm = self._normalize_text(story.get("headline"))
        section_norm = self._normalize_text(story.get("section"))
        published = story.get("published")

        if published and section_norm:
            date_bucket = str(published)[:10]
            return (headline_norm, date_bucket, section_norm)

        if published:
            date_bucket = str(published)[:10]
            return (headline_norm, date_bucket)

        return (headline_norm,)

    def _pick_richer_story(self, a: dict, b: dict) -> dict:
        score_a = self._story_richness_score(a)
        score_b = self._story_richness_score(b)

        depth_a = a.get("provenance", {}).get("crawl_depth")
        depth_b = b.get("provenance", {}).get("crawl_depth")

        depth_a_val = depth_a if isinstance(depth_a, int) else 999
        depth_b_val = depth_b if isinstance(depth_b, int) else 999

        if depth_a_val < depth_b_val:
            return a
        if depth_b_val < depth_a_val:
            return b

        return a if score_a >= score_b else b

    def _story_richness_score(self, story: dict) -> int:
        return sum(
            [
                1 if story.get("subheadline") else 0,
                1 if story.get("comment_count") is not None else 0,
                min(len(story.get("body_snippet") or "") // 80, 4),
                len(story.get("tags") or []),
            ]
        )

    def _extract_opinion_author(self, block: list[str], source_profile: dict) -> str | None:
        labels = set(source_profile.get("opinion_labels", []))
        for idx, line in enumerate(block):
            if line in labels and idx > 0:
                candidate = block[idx - 1].strip()
                if _AUTHOR_RE.match(candidate):
                    return candidate
        return None

    def _normalize_text(self, value: Any) -> str:
        if not value:
            return ""
        return re.sub(r"\s+", " ", str(value).strip().lower())
