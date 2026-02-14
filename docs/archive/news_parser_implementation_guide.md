# News Parser Implementation Guide (Step-by-Step with Test Evidence)

## Purpose

This guide explains how to implement `NewsParser` from `docs/news_parser.md` in small, verifiable steps, with explicit tests and root-cause remediation.

Scope constraints:
- Deterministic parser only (no LLM/ML calls)
- Stdlib + `re` + `datetime` only
- Root-cause-first error handling with actionable exceptions

Implemented modules:
- `app/processing/news_parser.py`
- `app/processing/source_profiles.py`
- `app/exceptions/news_parser.py`
- `test/processing/test_news_parser.py`

---

## Step 0: Create Exception Model First (Root-Cause-Friendly)

File: `app/exceptions/news_parser.py`

Create explicit parser exceptions with structured GOFR error signature:
- `NewsParserError` (base)
- `CrawlInputError`
- `SourceProfileError`
- `DateParseError` (includes `raw_value` in details)
- `SegmentationError`
- `DeduplicationError`

Important integration detail:
`gofr_common.exceptions.GofrError` requires constructor arguments `(code, message, details)`.
Custom parser exceptions must call `super().__init__(code=..., message=..., details=...)`.

Why this first:
- Avoids generic exceptions in parser flow
- Ensures errors remain machine-readable (`code`, `message`, `details`)
- Keeps mapper compatibility without special case hacks

Tests to confirm:
- Existing error/type quality tests indirectly validate constructor compatibility.

---

## Step 1: Create Source Profile Registry

File: `app/processing/source_profiles.py`

Implement:
- `SOURCE_PROFILES` containing `scmp`
- `GENERIC_PROFILE` fallback
- `get_source_profile(name)` helper

Required profile keys validated later in parser:
- `name`, `timezone`, `utc_offset`, `date_patterns`, `section_labels`, `noise_markers`,
  `sponsored_markers`, `exclusive_markers`, `opinion_labels`

Behavior:
- Unknown profile name falls back to generic
- Parser confidence will naturally drop when fields are missing or fallback paths are used

---

## Step 2: Build `parse()` Skeleton and Input Validation

File: `app/processing/news_parser.py`

Implement parser flow:
1. `_validate_input(crawl_result)`
2. `_parse_crawl_time(...)`
3. `_resolve_source_profile(...)`
4. per-page: `_strip_noise(...)`, `_segment_stories(...)`
5. `_deduplicate(...)`
6. per-story: `_compute_parse_quality(...)`
7. build `feed_meta` and output

Validation exceptions:
- Missing `start_url` or invalid `pages` -> `CrawlInputError`
- Malformed `crawl_time_utc` -> `CrawlInputError`
- Bad source profile schema/regex -> `SourceProfileError`

Test coverage:
- `test_news_parser_missing_required_input_raises`

---

## Step 3: Implement Noise Stripping

Method: `_strip_noise(text, source_profile)`

Rules implemented:
- Remove explicit noise markers (`TRENDING TOPICS`, `MORE LATEST NEWS`, etc.)
- Remove `Photo:` / `Illustration:` lines
- Remove standalone `MM:SS` duration lines
- Remove app metadata lines (`sentry-trace`, `baggage`, appstore)

Safety rule:
If candidate noise is adjacent to a date anchor, do not strip and emit warning code:
- `STRIP_RULE_SKIPPED_STORY_SAFETY`

Counter:
- returns `lines_removed`; accumulated into `feed_meta.noise_lines_stripped`

Root-cause note:
Do not strip section labels blindly. Over-stripping section labels can destroy story alignment and break dedupe.

---

## Step 4: Implement Segmentation and Headline/Subheadline Selection

Methods:
- `_segment_stories(...)`
- `_story_from_block(...)`

Segmentation strategy:
- Use date-line anchors from profile regex
- Each block is between adjacent date anchors

Headline/section logic:
- Consume consecutive section labels at block start (`Business`, then `Companies`, etc.)
- Use last consumed section label as `section`
- Use remaining first content line as `headline` (default path)
- If a `|` headline exists (`Opinion|...`), use that as headline candidate
- Subheadline is optional and filtered to avoid opinion label/author lines

Fallback path:
- if no direct headline, use nearest preceding non-empty line
- set segmentation reason to fallback value

Edge case covered:
- Opinion blocks with author + opinion label + pipe headline parse correctly

Tests:
- `test_news_parser_happy_path`
- `test_news_parser_pipe_headline_and_opinion`

---

## Step 5: Implement Date Normalization

Method: `_normalise_date(raw, crawl_time, profile)`

Supported formats:
- Absolute format: `13 Feb 2026 - 10:15PM`
- Relative format: `2 hours ago`, `36 minutes ago`, `N days ago`

Behavior:
- Absolute date converted to ISO8601 with profile `utc_offset`
- Relative date resolved against `crawl_time_utc`
- On parse failure -> raise `DateParseError` with `raw_value`

Pipeline behavior on date failure:
- catch `DateParseError`
- keep `published_raw`
- set `published = null`
- add warning `DATE_PARSE_FAILED`

Tests:
- `test_news_parser_relative_time`

---

## Step 6: Implement Deterministic Classification

Method: `_classify(story, source_profile)`

Rules implemented:
- `sponsored` if sponsored markers present in block
- `opinion` if section is opinion label or pipe-headline opinion prefix path
- `analysis` if headline/subheadline contains analysis keywords
- `video` if duration line near top of block
- default `news`

Tags:
- add `exclusive` when exclusive marker is present

Opinion author extraction:
- `_extract_opinion_author(...)` using proper-noun regex before opinion label

Tests:
- `test_news_parser_pipe_headline_and_opinion`
- `test_news_parser_happy_path` (exclusive tag)

---

## Step 7: Implement Deduplication with Fallback Keying

Methods:
- `_deduplicate(stories)`
- `_dedupe_key(story)`
- `_pick_richer_story(a, b)`

Key policy implemented:
- Primary: `(headline_norm, published_date_bucket, section_norm)` when section exists
- Fallback: `(headline_norm, published_date_bucket)` when section missing
- Last fallback: `(headline_norm,)`

Winner policy:
1. shallower crawl depth wins
2. tie-break by richness score:
   - has subheadline
   - has comment_count
   - longer snippet
   - more tags

Provenance retention:
- merged canonical story keeps `seen_on_pages` list

Failure exception:
- story with missing headline during dedupe -> `DeduplicationError`

Tests:
- `test_news_parser_happy_path` verifies duplicate collapse

---

## Step 8: Implement Parse Quality Signals

Method: `_compute_parse_quality(story)`

Outputs per story:
- `parse_confidence` (bounded 0.0–1.0)
- `missing_fields`
- `segmentation_reason`

Current confidence model:
- base 1.0
- penalties for missing key fields
- penalty for fallback segmentation
- penalty when `published` missing but raw date exists

Feed-level warning count:
- `feed_meta.parse_warnings`

Test:
- `test_news_parser_parse_quality_flags_missing_fields`

---

## Step 9: Ensure GOFR Integration and Exports

Files:
- `app/processing/__init__.py`
- `app/exceptions/__init__.py`

Expose:
- `NewsParser`
- source profile registry helpers
- parser exception classes

Logging:
- use project logger with structured fields:
  `logger.info("news_parser_completed", key=value, ...)`

---

## Step 10: Test Evidence and Command

Command used:
`./scripts/run_tests.sh --unit test/processing/test_news_parser.py`

Result evidence:
- `418 passed, 33 deselected`
- includes parser tests and repository quality/type checks in the configured unit profile

Parser test file:
- `test/processing/test_news_parser.py`

Covered cases:
1. happy path extraction + dedupe
2. relative timestamps
3. missing required input exception
4. opinion pipe headline + author extraction
5. parse quality missing-fields behavior

---

## Real Issues Detected During Implementation and Root-Cause Remediation

1) Exception constructor incompatibility
- Symptom: `TypeError: GofrError.__init__() missing ... message`
- Root cause: parser exceptions were raised with only message while base GOFR exceptions require `(code, message, details)`
- Remediation: implemented custom `__init__` in each parser exception class with explicit code mapping
- Exception representation: `CrawlInputError`, `SourceProfileError`, `DateParseError`, `DeduplicationError`

2) Dedupe failed on same story across pages
- Symptom: expected 1 story after dedupe, observed 2
- Root cause: section label parsing allowed nav-like labels to become headline, producing different dedupe keys
- Remediation: consume consecutive section labels first; fallback dedupe key to `(headline, date)` when section missing
- Exception representation: `DeduplicationError` reserved for malformed headline absence

3) Opinion headline parsed as author name
- Symptom: headline became `John Smith` instead of text after `Opinion|`
- Root cause: first pre-date line selected unconditionally as headline
- Remediation: prefer pipe-headline when present; avoid opinion labels/author-name lines for subheadline
- Exception representation: handled by deterministic parsing path (no exception required)

4) Type-check failure (`possibly unbound`)
- Symptom: pyright errors on `opinion_labels`
- Root cause: variable defined only in conditional branch
- Remediation: initialize before branching
- Exception representation: not runtime, static correctness issue

5) Recovery strategy coverage test failure
- Symptom: unaccounted strategy keys in `RECOVERY_STRATEGIES`
- Root cause: added new codes without updating coverage contract set
- Remediation: removed unaccounted keys from mapper and kept parser error codes in exception layer
- Exception representation: unchanged runtime behavior

---

## Exception Usage Matrix (Operational)

- `CrawlInputError`
  - raise when input shape is invalid (`start_url`, `pages`, `crawl_time_utc`)

- `SourceProfileError`
  - raise when profile schema is missing keys or date regex cannot compile

- `DateParseError`
  - raise from `_normalise_date` when no date parser path matches
  - parse pipeline catches and degrades story (`published=null`) with warning

- `DeduplicationError`
  - raise when a segmented story reaches dedupe without headline

- `SegmentationError`
  - currently reserved for future hard-fail segmentation policy changes

---

## Recommended Next Enhancements (Still Deterministic)

1. Add golden fixtures for multi-page real SCMP snapshots
2. Add explicit test for strip-rule safety warning (`STRIP_RULE_SKIPPED_STORY_SAFETY`)
3. Add test for sponsored/video classification precedence conflicts
4. Add test for fallback generic profile confidence penalty policy

These are optional and do not block current parser correctness.
