# Source Profiles — Reference and Authoring Guide

Source profiles are pure-data configuration dicts that tell the news parser how to
handle a specific news site. They control noise stripping, date parsing, section
recognition, opinion detection, and content classification — without any code branches.

This document covers:

1. Profile schema (every field explained)
2. How the parser uses each field
3. How to add a new profile
4. LLM prompt for proposing a profile from a raw scrape


---

## 1. Profile Schema

Every profile is a Python dict with these keys. All list fields default to `[]` if
omitted, so only `name`, `date_patterns`, `timezone`, and `utc_offset` are truly
required.

```
{
    "name":               str,        # REQUIRED — short lowercase slug, used in story_id hashes
    "display_name":       str,        # Human-readable site name (shown in feed_meta.source_name)
    "timezone":           str,        # IANA timezone, e.g. "Asia/Hong_Kong", "America/New_York"
    "utc_offset":         str,        # Fixed offset string, e.g. "+08:00", "-05:00"
    "date_patterns":      [str, ...], # REQUIRED — regex patterns that match date/timestamp lines
    "section_labels":     [str, ...], # Exact strings that appear as section/category labels
    "noise_markers":      [str, ...], # Exact strings for navigation/promo lines to strip
    "sponsored_markers":  [str, ...], # Exact strings that mark sponsored/paid content
    "exclusive_markers":  [str, ...], # Exact strings that mark exclusive stories (becomes a tag)
    "opinion_labels":     [str, ...], # Exact strings that indicate opinion/commentary content
}
```


## 2. How the Parser Uses Each Field

| Field | Parser behaviour |
|---|---|
| `name` | Embedded in every `story_id` hash. Appears in `feed_meta.source_profile`. |
| `display_name` | Copied to `feed_meta.source_name`. Falls back to `name` if absent. |
| `timezone` / `utc_offset` | `utc_offset` is used to attach timezone info to parsed absolute dates. `timezone` is metadata (not currently used for calculation, but documents intent). |
| `date_patterns` | Compiled into a single regex. Every line in the crawl text is tested against it. Matching lines become "date anchors" that segment the text into story blocks. **This is the most critical field** — if it doesn't match, zero stories are extracted. |
| `section_labels` | Lines matching these (exact, case-sensitive) at the start of a story block are extracted as the `section` field and removed from headline consideration. |
| `noise_markers` | Lines matching these (exact, case-sensitive) are stripped during the noise-removal pass before story segmentation. |
| `sponsored_markers` | Lines matching these cause the story to get `content_type: "sponsored"` and the line is removed from headline consideration. |
| `exclusive_markers` | Lines matching these add an `"exclusive"` tag to the story and the line is removed from headline consideration. |
| `opinion_labels` | If a story's section matches one of these, or the headline starts with `"Opinion|"`, the story gets `content_type: "opinion"` and the parser attempts to extract an author. |


## 3. How to Add a New Profile

### Step 1 — Create the profile dict

Open `app/processing/source_profiles.py` and add a new entry to `SOURCE_PROFILES`:

```python
SOURCE_PROFILES: dict[str, dict] = {
    "scmp": { ... },  # existing

    "reuters": {
        "name": "reuters",
        "display_name": "Reuters",
        "timezone": "UTC",
        "utc_offset": "+00:00",
        "date_patterns": [
            r"\w+\s+\d{1,2},?\s+\d{4}\s+\d{1,2}:\d{2}\s*[AP]M\s+UTC",
            r"\d+\s+(minutes?|hours?|days?)\s+ago",
        ],
        "section_labels": ["Markets", "World", "Business", "Technology"],
        "noise_markers": ["TRENDING", "MORE FROM REUTERS", "ADVERTISEMENT"],
        "sponsored_markers": ["Sponsored:"],
        "exclusive_markers": ["Exclusive"],
        "opinion_labels": ["Opinion", "Commentary", "Breakingviews"],
    },
}
```

### Step 2 — Write a fixture test

Create a snapshot HTML fixture in `test/fixtures/` with a representative page from
the site. Write a test in `test/scraping/` that calls the parser with that fixture
and the new profile name, then asserts on expected story count, headline extraction,
date parsing, and section assignment.

### Step 3 — Run tests

```bash
./scripts/run_tests.sh --unit test/scraping/test_<site>_parser.py
./scripts/run_tests.sh   # full suite to confirm no regressions
```

### Step 4 — Use it

Pass `source_profile_name: "<name>"` in the `get_content` MCP tool call when
scraping that site. If omitted, the parser uses the `"generic"` fallback.


## 4. LLM Prompt for Proposing a Source Profile

Use the prompt below with any LLM. Paste a raw scrape (the text content from
`get_content` with `parse_results: false`) as the input. The LLM will analyse the
patterns and propose a complete source profile dict.

---

### Prompt

```
You are a configuration analyst for a deterministic news parser. Your job is to
examine raw scraped text from a news website and propose a source_profile — a
pure-data configuration dict that tells the parser how to segment, classify, and
clean stories from this site.

The parser works as follows:
1. Noise stripping — lines matching noise_markers are removed entirely.
2. Story segmentation — lines matching date_patterns become "date anchors". The
   text between consecutive date anchors forms one story block.
3. Within each story block, lines before the date anchor are checked:
   - Lines matching section_labels are extracted as the section.
   - Lines matching sponsored_markers or exclusive_markers are stripped and used
     for classification/tagging.
   - The remaining pre-date lines become the headline (and optionally subheadline).
4. Lines after the date anchor become the body snippet.
5. Classification — if the section matches an opinion_label, the story is marked
   as opinion content and an author extraction is attempted.

IMPORTANT CONSTRAINTS:
- date_patterns are Python regex patterns. They must match the ENTIRE date/time
  string as it appears on its own line (or as a recognisable substring). Include
  both absolute date formats AND relative timestamps ("X minutes ago") if present.
- All label/marker fields are EXACT string matches (case-sensitive). They must
  match the text as it literally appears in the scrape.
- The profile must be pure data — no code, no lambdas, no functions.

Analyse the following raw scrape and produce a source_profile dict.

For each field, explain your reasoning in a comment, then give the value.
After the profile dict, list:
- Any patterns you are uncertain about (with examples from the text).
- Suggested test cases: 3-5 specific stories from the scrape with their expected
  headline, section, published date, and content_type, so the developer can write
  fixture tests.

---

RAW SCRAPE:

<paste the raw text output from get_content with parse_results=false here>
```

---

### Example LLM output (abbreviated)

```python
{
    "name": "bbc",
    "display_name": "BBC News",
    "timezone": "Europe/London",
    "utc_offset": "+00:00",

    # Dates appear as "14 February 2026" or "2 hours ago"
    "date_patterns": [
        r"\d{1,2}\s+\w+\s+\d{4}",
        r"\d+\s+(minutes?|hours?|days?)\s+ago",
    ],

    # These appear as standalone lines above story groups
    "section_labels": ["UK", "World", "Business", "Sport", "Technology", "Science"],

    # Navigation/promo text that appears between stories
    "noise_markers": [
        "MORE STORIES",
        "WATCH LIVE",
        "BBC NEWS SERVICES",
    ],

    "sponsored_markers": [],
    "exclusive_markers": [],

    # "Analysis" label appears before some author bylines
    "opinion_labels": ["Analysis", "Opinion"],
}

# UNCERTAINTIES:
# - "14 February 2026" may also appear with time: "14 February 2026, 10:30 GMT"
#   I only saw the date-only variant. If the timed variant exists, add:
#   r"\d{1,2}\s+\w+\s+\d{4},?\s+\d{1,2}:\d{2}\s+\w+"
#
# SUGGESTED TEST CASES:
# 1. Headline: "UK economy grows faster than expected"
#    Section: "Business"
#    Published: "14 February 2026"
#    Content type: "news"
# 2. ...
```

### How to use the output

1. Copy the proposed dict into `app/processing/source_profiles.py`.
2. Validate the `date_patterns` against 5–10 date lines from the scrape using a
   Python regex tester (or `re.search(pattern, line)`).
3. Spot-check `section_labels` and `noise_markers` against the raw text — look for
   case mismatches or partial matches.
4. Use the suggested test cases to write fixture tests.
5. Run the parser with `parse_results: true, source_profile_name: "<name>"` on the
   same URL and compare the output against expectations.


## 5. Existing Profiles

| Profile | Name | Display Name | Timezone |
|---|---|---|---|
| `scmp` | scmp | South China Morning Post | Asia/Hong_Kong (+08:00) |
| `generic` | generic | Unknown Source | UTC (+00:00) |

The `generic` profile is the automatic fallback. It has broad date patterns and
empty section labels. It works for many sites but produces lower parse quality
because it cannot distinguish section labels from headlines.
