# news_parser — Post-Processing Spec

## Goal

Transform raw gofr-dig crawl output into a clean, structured news feed that an LLM can
consume directly for story analysis and force-ranking — no hallucination-inducing noise,
maximum detail preserved, full provenance on every item. Zero LLM calls in this pipeline.

Design principle: deterministic parsing with explainable outcomes. Every story should either
parse cleanly or carry machine-readable quality signals that explain what was missing.


## Input

Standard gofr-dig `get_content` result (depth crawl). Structure per page:

    page.url        — full page URL
    page.title      — <title> tag
    page.text       — flat newline-delimited blob (all visible text)
    page.headings[] — [{level, text}, ...] from <h1>–<h6>
    page.meta{}     — og:*, description, keywords, etc.
    page.depth      — crawl depth (1 = seed, 2+ = followed links)

Top-level fields: `start_url`, `crawl_depth`, `max_pages_per_level`, `summary`.

Parser runtime input:

    crawl_time_utc      — parser invocation timestamp in UTC (required)
    parser_version      — semantic version string for reproducibility (required)
    source_profile_name — site profile key (e.g. "scmp")


## Source Profile

Site-specific rules are configuration, not code branches. Add a `source_profile` object:

```json
{
  "name": "scmp",
  "timezone": "Asia/Hong_Kong",
  "date_patterns": [
    "\\d{1,2}\\s+\\w+\\s+\\d{4}\\s*-\\s*\\d{1,2}:\\d{2}[AP]M",
    "\\d+\\s+(minutes|hours)\\s+ago"
  ],
  "section_labels": ["Business", "Tech", "China Economy", "Banking & Finance", "Opinion"],
  "noise_markers": ["TRENDING TOPICS", "MOST POPULAR", "MORE LATEST NEWS", "MORE COMMENT"],
  "sponsored_markers": ["In partnership with:", "Paid Post:"],
  "exclusive_markers": ["Exclusive"],
  "opinion_labels": ["Opinion", "Macroscope", "As I see it"]
}
```

If no profile is supplied, parser must fall back to a safe generic profile and lower
`parse_confidence` for affected stories.


## Output

```json
{
  "feed_meta": {
    "parser_version": "1.0.0",
    "source_profile": "scmp",
    "source_name": "South China Morning Post",
    "source_root_url": "https://www.scmp.com/business",
    "crawl_time_utc": "2026-02-14T10:30:00Z",
    "pages_crawled": 6,
    "stories_extracted": 24,
    "duplicates_removed": 7,
    "noise_lines_stripped": 185,
    "parse_warnings": 3
  },
  "stories": [
    {
      "story_id": "scmp:5f4e8a...",
      "headline": "Meituan warns of US$3.5 billion loss amid intense food delivery price war",
      "subheadline": null,
      "section": "Companies",
      "published": "2026-02-13T22:15:00+08:00",
      "published_raw": "13 Feb 2026 - 10:15PM",
      "body_snippet": "...",
      "comment_count": null,
      "tags": ["exclusive"],
      "content_type": "news",
      "parse_quality": {
        "parse_confidence": 0.96,
        "missing_fields": [],
        "segmentation_reason": "date_anchor+heading_alignment"
      },
      "provenance": {
        "root_url": "https://www.scmp.com/business",
        "page_url": "https://www.scmp.com/business?module=oneline_menu_section_int&pgtype=homepage",
        "crawl_depth": 1
      }
    }
  ]
}
```


## Processing Pipeline

### 1. Noise Stripping

Remove lines matching these patterns from the flat text blob before any parsing:

| Category         | Pattern / Rule                                        |
|------------------|-------------------------------------------------------|
| Navigation       | Repeated section menu labels (Business, Companies, Markets, ...) appearing as nav |
| Photo captions   | Lines matching `Photo: *` or `Illustration: *`        |
| Sponsored        | Lines preceded by "In partnership with:" or "Paid Post:" |
| Trending         | Remove only the trending/popular module block itself; do not strip beyond the next validated story boundary |
| Video durations  | Standalone lines matching `\d{2}:\d{2}` (e.g. "07:39") |
| App metadata     | Lines containing app store IDs, sentry-trace, baggage  |
| Pagination       | "MORE LATEST NEWS", "MORE COMMENT", etc.              |

Counters: track `noise_lines_stripped` for feed_meta.

Safety rule: if a strip rule would remove lines that include a valid date anchor and headline,
do not strip and emit a parse warning.


### 2. Story Segmentation

Parse the cleaned text into discrete story blocks using a date-anchored pattern:

    [SECTION_LABEL]          ← optional, a known section name (level-2 heading that is NOT a headline)
    HEADLINE                 ← level-2 heading text (the article title)
    SUBHEADLINE              ← optional, level-3 heading text (the deck/standfirst)
    DATE_LINE                ← required anchor: regex `\d{1,2}\s+\w+\s+\d{4}\s*-\s*\d{1,2}:\d{2}[AP]M`
    [COMMENT_COUNT]          ← optional trailing integer on its own line

A story block is everything between two consecutive date-anchored boundaries.

Section labels vs headlines — distinguish by maintaining a known-sections list extracted from
the seed page's nav (level-2 headings that repeat across pages: "Tech", "Business",
"China Economy", "Banking & Finance", etc.). Any level-2 heading NOT in that set is a headline.

If heading alignment fails, fallback segmentation is date-anchor-first with nearest preceding
non-empty line as candidate headline and reduced `parse_confidence`.


### 3. Subheadline Pairing

Match level-3 headings to their parent story by position:

- If a level-3 heading appears between a level-2 headline and the next date line, it is
  the subheadline/standfirst for that story.
- Only first match; additional level-3 entries are body text.


### 4. Date Normalisation

Parse the raw date string into ISO 8601 with the source timezone offset (SCMP = +08:00).
Also handle relative timestamps ("2 hours ago", "36 minutes ago") by computing against
crawl_time_utc. Preserve `published_raw` verbatim for audit.

Clock precedence:
1) explicit parser `crawl_time_utc`
2) page fetch timestamp if available
3) if neither exists, keep `published=null`, add parse warning


### 5. Deduplication

Stories appear on multiple crawled pages (section index + subsection pages).

- Primary key: `norm_headline + published_date_bucket + section` where available.
- Secondary fallback: `norm_headline` only when date/section are missing.
- On collision: keep shallowest depth; if tied, keep richer record by score:
  `has_subheadline + has_comment_count + longer_body_snippet + more_tags`.
- Track `duplicates_removed` count.


### 6. Content Classification

Tag each story with a `content_type` — no ML, just rules:

| Type       | Rule                                                        |
|------------|-------------------------------------------------------------|
| `opinion`  | Section is "Opinion", "Macroscope", "As I see it", or headline has "Opinion\|" prefix |
| `analysis` | Subheadline or headline contains "analysis", "deep dive", "explainer" |
| `video`    | Preceded by a standalone duration line (MM:SS)              |
| `sponsored`| Preceded by "In partnership with:" or "Paid Post:"         |
| `news`     | Default                                                     |

Also extract tags: `["exclusive"]` if "Exclusive" label precedes headline.

Classification must be idempotent and deterministic: same input story always yields same
`content_type` and tags.


### 7. Provenance

Every story carries:

- `root_url` — the `start_url` from the crawl (seed page the user targeted)
- `page_url` — the specific `page.url` where this story instance was found
- `crawl_depth` — the `page.depth` value

This lets the LLM or downstream consumer trace any story back to its source page
and understand how far it was from the seed URL.

Provenance fields are required and must never be dropped during dedupe. Dedupe merges content
into a chosen canonical story but retains a `seen_on_pages` list optionally for audit.


### 8. Opinion Author Extraction

For opinion pieces, extract the author name from the line immediately preceding the
column/section label. Pattern: a proper-noun line (2-3 capitalised words) followed by
"Opinion", "Macroscope", "As I see it", etc.

Store as `author` field (null for non-opinion content_types).


### 9. Parse Quality Signals

Each story must include:

- `parse_confidence` (0.0 to 1.0)
- `missing_fields` (e.g. `published`, `section`, `subheadline`)
- `segmentation_reason` (rule path used)

Feed-level aggregation:

- `parse_warnings` count in `feed_meta`
- optional `warnings[]` list with compact codes and examples


## Non-Goals

- No summarisation or rephrasing (that is the LLM's job)
- No sentiment analysis
- No entity extraction (LLM downstream)
- No full-article fetch (parser works only on what the crawl returned)
- No external API calls


## Output Contract

Required story fields:

- `story_id`, `headline`, `content_type`, `provenance.root_url`, `provenance.page_url`, `provenance.crawl_depth`, `parse_quality`

Nullable story fields:

- `subheadline`, `section`, `published`, `comment_count`, `author`

Contract rules:

- Unknown values use `null`, never empty-string placeholders
- Preserve `published_raw` when present even if `published` is null
- Preserve original casing in display fields; normalised forms are internal only
- Emit `parser_version` and `source_profile` in `feed_meta` for reproducibility


## Implementation

Module: `app/processing/news_parser.py`

```
class NewsParser:
    def parse(self, crawl_result: dict) -> dict:
        """Main entry — takes raw get_content result dict, returns feed dict."""

  def _resolve_source_profile(self, crawl_result: dict) -> dict:
    """Returns source profile configuration used by parser."""

    def _strip_noise(self, text: str) -> tuple[str, int]:
        """Returns (cleaned_text, lines_removed)."""

    def _segment_stories(self, cleaned_text: str, headings: list, meta: dict) -> list[dict]:
        """Returns list of raw story dicts."""

    def _normalise_date(self, raw: str, crawl_time: datetime) -> str:
        """Returns ISO 8601 string."""

    def _deduplicate(self, stories: list[dict]) -> tuple[list[dict], int]:
        """Returns (unique_stories, duplicates_removed)."""

    def _classify(self, story: dict) -> str:
        """Returns content_type string."""

    def _build_provenance(self, page: dict, start_url: str) -> dict:
        """Returns provenance dict for a story."""

    def _compute_parse_quality(self, story: dict) -> dict:
      """Returns parse quality payload for a story."""
```

No dependencies beyond stdlib + `re` + `datetime`. Must not import any LLM or ML library.


## Edge Cases

- Pages with zero stories (e.g. a subsection that only has nav + trending) → skip, do not
  emit empty story objects
- Headlines containing pipe characters ("Opinion|Why China...") → split on first `|`, treat
  left side as section/tag, right side as headline text
- Relative timestamps without a crawl_time_utc reference → fall back to `published_raw` only,
  set `published` to null
- Non-English pages → pass through unchanged, set `language` field from page data
- Same headline reused for separate updates on different days → do not merge if date bucket differs
- Strip-rule ambiguity (could be module text or article text) → keep content and lower confidence
