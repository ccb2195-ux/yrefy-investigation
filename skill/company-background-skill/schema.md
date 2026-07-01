# Company Background Skill — Data Schema Reference

This document describes every data structure that flows through the
company-background-skill: raw tool inputs and outputs, what fields are
extracted at each step, how data is transformed into the internal model,
and how the internal model maps to the HTML report.

It is meant to be read alongside `SKILL.md` (which describes *what* to do)
and serves as a reference for anyone extending the skill, debugging unexpected
results, or building downstream pipelines on top of its output.

---

## Table of Contents

1. [Overall Data Flow](#1-overall-data-flow)
2. [Step 1 — Target Clarification](#2-step-1--target-clarification)
3. [Step 2 — GDELT Adverse Media](#3-step-2--gdelt-adverse-media)
4. [Step 3 — OpenSanctions Screening](#4-step-3--opensanctions-screening)
5. [Step 4 — SEC EDGAR Filings](#5-step-4--sec-edgar-filings)
6. [Step 5 — CourtListener Litigation](#6-step-5--courtlistener-litigation)
7. [Step 6 — Enigma Deep-Dive](#7-step-6--enigma-deep-dive)
8. [Step 7 — Internal Data Model](#8-step-7--internal-data-model)
9. [Step 8 — HTML Report Schema](#9-step-8--html-report-schema)
10. [Field Vocabulary](#10-field-vocabulary)
11. [Coverage Gap Taxonomy](#11-coverage-gap-taxonomy)

---

## 1. Overall Data Flow

```
User input (company name / jurisdiction)
        │
        ▼
Step 1: TARGET RECORD
        │  { legal_name, aliases[], jurisdiction, hq_address, assumptions[] }
        │
        ├──────────────────────────────────────────────────────────────────┐
        ▼                                                                  ▼
Step 2: GDELT                                                    Step 3: OpenSanctions
  { articles[], tone_timeline[] }                          { matches[], entity_records[] }
        │                                                                  │
        ├────────────────┐                         ┌─────────────────────┘
        ▼                ▼                         ▼
Step 4: EDGAR      Step 5: CourtListener    Step 6: Enigma
  { filings[] }      { dockets[] }          { brand, kyb, gov_archive,
                                              negative_news, legal_entities,
                                              card_analytics }
        │                │                         │
        └────────────────┴─────────────────────────┘
                                 │
                                 ▼
                    Step 7: INTERNAL DATA MODEL
                    { target, entities[], timeline[],
                      known_facts[], allegations[],
                      key_leads[], coverage_gaps[] }
                                 │
                                 ▼
                    Step 8: HTML REPORT FILE
                    (self-contained, written to disk)
```

Each step produces a typed output record. Steps 2–6 run in parallel where
possible. Step 7 is the synthesis gate — nothing is written to the HTML
until all available upstream data has been collected and normalized.

---

## 2. Step 1 — Target Clarification

### Purpose
Resolve the user's input to a canonical legal entity before any API calls
are made. A wrong-entity match downstream (e.g. a common-name company in
the wrong country) is worse than no match.

### Input
```
user_input: string   # Free-form company name or person name as typed
```

### Output — TARGET RECORD
```json
{
  "legal_name":    "string  — canonical legal name (e.g. 'Yrefy LLC')",
  "aliases":       ["string — known trade names, DBAs, former names"],
  "jurisdiction":  "string  — state or country of incorporation",
  "hq_address":    "string  — full street address if known",
  "entity_type":   "string  — 'Company' | 'Person' | 'Organization'",
  "assumptions":   ["string — any disambiguation choices made, flagged for the report"]
}
```

### Notes
- If the user-supplied name differs from the canonical legal name (e.g.
  "Yrefi" → "Yrefy LLC"), the correction and the basis for it must be
  recorded in `assumptions[]` and surfaced in the report header.
- `hq_address` populated here is reused verbatim as the `address` parameter
  for `enigma.search_negative_news` in Step 6d.
- `entity_type` drives the `schema` parameter for all OpenSanctions calls.

---

## 3. Step 2 — GDELT Adverse Media

### Tools
`gdelt.search_news` · `gdelt.search_news_tone`

### 3a. `search_news`

**Endpoint:** `GET https://api.gdeltproject.org/api/v2/doc/doc`

**Parameters sent:**
```
query       string   Entity name in quotes, e.g. '"Yrefy LLC"'
mode        string   Always "artlist"
maxrecords  int      1–250 (default 25)
timespan    string   "3months" | "1month" | "1week" | date range
sort        string   "hybridrel" | "datedesc" | "dateasc"
format      string   Always "json"
```

**Raw API response shape:**
```json
{
  "articles": [
    {
      "url":           "string",
      "url_mobile":    "string",
      "title":         "string",
      "seendate":      "string  — YYYYMMDDTHHMMSSZ format",
      "socialimage":   "string  — optional thumbnail URL",
      "domain":        "string  — e.g. 'reuters.com'",
      "language":      "string  — ISO 639-1 code, e.g. 'English'",
      "sourcecountry": "string  — e.g. 'United States'"
    }
  ]
}
```

**Fields extracted and stored:**
```json
{
  "title":         "string",
  "url":           "string",
  "domain":        "string",
  "seendate":      "string  — normalized to YYYY-MM-DD for display",
  "language":      "string",
  "sourcecountry": "string"
}
```

**Fields discarded:** `url_mobile`, `socialimage` (not used in report)

**Error shape (rate-limited or server error):**
```json
{
  "error":  "string  — e.g. 'GDELT returned HTTP 429'",
  "detail": "string  — raw response body, truncated to 500 chars"
}
```

A 429 means GDELT's rate limit was hit (one request per 5 seconds for
the free DOC API). When this occurs, the step is recorded as a coverage
gap and web search is substituted for recent coverage.

---

### 3b. `search_news_tone`

**Parameters sent:**
```
query    string   Same query syntax as search_news
mode     string   Always "timelinetone"
timespan string   Same as search_news
format   string   Always "json"
```

**Raw API response shape:**
```json
{
  "timeline": [
    {
      "date":  "string  — YYYYMMDDTHHMMSSZ",
      "value": "float   — average tone score for that period"
    }
  ]
}
```

**How tone scores are interpreted:**
```
value < -5    Strongly negative coverage — investigate this window
-5 to -2      Moderately negative
-2 to  0      Slightly negative (normal for business coverage)
 0 to  2      Neutral to mildly positive
 value > 2    Unusually positive — possible puff pieces or PR campaigns
```

**Use in workflow:** Identify date windows where `value < -5`. Re-run
`search_news` with `timespan` narrowed to that window to find specific
articles. The tone timeline itself does not appear in the report; only
the resulting article findings do.

---

### Step 2 Stored Output
```json
{
  "articles": [
    {
      "title":       "string",
      "url":         "string",
      "domain":      "string",
      "date":        "string  — YYYY-MM-DD",
      "language":    "string",
      "adverse":     "boolean — manually assessed: does this article describe risk?"
    }
  ],
  "themes": ["string — summarized adverse media themes"],
  "gap":    "boolean — true if GDELT was rate-limited or returned no results"
}
```

---

## 4. Step 3 — OpenSanctions Screening

### Tools
`opensanctions.match_entity` · `opensanctions.search_entity` · `opensanctions.get_entity`

### Authentication
Requires `OPENSANCTIONS_API_KEY` environment variable. Set in
`mcp-servers/opensanctions/.env`. Free for journalism, academic research,
anti-corruption work. Commercial use requires a data license.

### 4a. `match_entity` (primary screening tool)

**Endpoint:** `POST https://api.opensanctions.org/match/default`

**Request body:**
```json
{
  "queries": {
    "q1": {
      "schema": "Company | Person | Organization",
      "properties": {
        "name":      ["string — legal name"],
        "country":   ["string — ISO 3166-1 alpha-2, e.g. 'us'"],
        "birthDate": ["string — YYYY-MM-DD, Person only"]
      }
    }
  }
}
```

**Raw response shape:**
```json
{
  "responses": {
    "q1": {
      "results": [
        {
          "id":         "string  — OpenSanctions entity ID, e.g. 'NK-abc123'",
          "caption":    "string  — display name",
          "schema":     "string  — entity type",
          "score":      "float   — match confidence 0.0–1.0",
          "match":      "boolean — true if score exceeds the screening threshold",
          "properties": {
            "topics":   ["string — risk topic codes (see vocabulary below)"],
            "name":     ["string"],
            "country":  ["string"]
          },
          "datasets":   ["string — source dataset slugs, e.g. 'us_ofac_sdn'"]
        }
      ]
    }
  }
}
```

**Fields extracted:**
```json
{
  "id":       "string",
  "caption":  "string",
  "score":    "float",
  "match":    "boolean",
  "topics":   ["string"],
  "datasets": ["string"]
}
```

**Score interpretation:**
```
score >= 0.8   High-confidence match — treat as a hit, pull full record
score 0.5–0.8  Possible match — review caption and topics manually
score < 0.5    Low confidence — probably a different entity
```

**Topic codes and their meaning:**
```
sanction         Entity is directly sanctioned
sanction.linked  Associated with a sanctioned entity (not directly sanctioned)
role.pep         Politically Exposed Person
role.rca         Relative or Close Associate of a PEP
crime            Criminal record or conviction
crime.fin        Financial crime
crime.fraud      Fraud
debarment        Barred from government contracts or programs
export.control   Subject to export control restrictions
```

---

### 4b. `search_entity` (free-text fallback)

**Endpoint:** `GET https://api.opensanctions.org/search/default`

**Parameters:**
```
q      string   Free-text search query
limit  int      1–50
schema string   Optional entity type filter
```

**Response shape** (same structure as `match_entity` results but without
`score` and `match` fields — less suitable for compliance screening):
```json
{
  "results": [
    {
      "id":         "string",
      "caption":    "string",
      "schema":     "string",
      "topics":     ["string"],
      "datasets":   ["string"],
      "score":      "float  — relevance score, not match confidence"
    }
  ]
}
```

Use `match_entity` by default. Fall back to `search_entity` only if
`match_entity` returns zero results and you want to check for partial name
variants.

---

### 4c. `get_entity` (full record pull)

**Endpoint:** `GET https://api.opensanctions.org/entities/{entity_id}`

Call this on any `id` returned by `match_entity` with `score >= 0.5`.

**Response shape:**
```json
{
  "id":         "string",
  "caption":    "string",
  "schema":     "string",
  "properties": {
    "name":        ["string"],
    "country":     ["string"],
    "topics":      ["string"],
    "address":     ["string"],
    "sourceUrl":   ["string"],
    "program":     ["string — sanction program name, e.g. 'Executive Order 13694'"],
    "startDate":   ["string — YYYY-MM-DD when sanction began"],
    "endDate":     ["string — YYYY-MM-DD if lifted"],
    "family":      ["string — related person entity IDs"],
    "associates":  ["string — associated entity IDs"],
    "ownershipAncestor": ["string — parent/owner entity IDs"]
  },
  "datasets": ["string"],
  "referents": ["string — alternative IDs in source datasets"]
}
```

**Key fields for the report:**
- `properties.program` — name the specific sanction, not just that one exists
- `properties.startDate` / `endDate` — sanction period; active vs. lifted
- `properties.ownershipAncestor` — if the entity itself isn't sanctioned but
  its owner is, this is where you find the link (call `get_entity` on each ID)

---

### Step 3 Stored Output
```json
{
  "screened_name":  "string",
  "result":         "hit | no_hit | error",
  "matches": [
    {
      "id":       "string",
      "caption":  "string",
      "score":    "float",
      "topics":   ["string"],
      "datasets": ["string"],
      "full_record": { }
    }
  ],
  "gap": "boolean — true if API key missing or call failed"
}
```

A `result` of `"no_hit"` is meaningful — it must be reported explicitly as
"no adverse findings in OpenSanctions" rather than omitted.

---

## 5. Step 4 — SEC EDGAR Filings

### Tools
`WebFetch` against EDGAR full-text search, or `WebSearch` targeting `site:sec.gov`

### EDGAR Full-Text Search URL Pattern
```
https://efts.sec.gov/LATEST/search-index?q="ENTITY NAME"&forms=8-K,S-1,D
```

**No API key required.** Returns HTTP 403 in some environments (proxy/auth
issues). If 403, fall back to `WebSearch(query='site:sec.gov "Entity Name" 10-K 8-K')`.

### Form Types of Interest
```
Form D    Regulation D exempt offering notice — confirms private placement capital raises
          Filed within 15 days of first sale. Key fields: total offering amount,
          number of investors, date of first sale, exemption claimed.

8-K       Material event disclosure — litigation, restatements, investigations,
          changes in leadership, material agreements.

S-1       Registration statement — public offering intent. Presence = company
          is going/went public, or a subsidiary is.

10-K      Annual report (public companies only). Contains MD&A, risk factors,
          legal proceedings section — rich source of litigation and regulatory history.

AAER      Accounting and Auditing Enforcement Release — SEC enforcement against
          accountants or auditors; often co-occurs with fraud.
```

### Form D Data Schema (from SEC EDGAR)
```json
{
  "entityName":           "string",
  "cik":                  "string  — SEC Central Index Key",
  "dateOfFirstSale":      "string  — YYYY-MM-DD",
  "totalOfferingAmount":  "number  — USD",
  "totalAmountSold":      "number  — USD",
  "totalNumberAlreadySold": "number",
  "exemptionsUsed":       ["string — e.g. 'Rule 506(c)'"],
  "statesOfSolicitees":   ["string — state codes where investors were solicited"],
  "filingDate":           "string  — YYYY-MM-DD"
}
```

**Key signal from Form D:** The `statesOfSolicitees` field reveals every state
where the company has marketed to investors. States NOT listed are either
voluntarily excluded or barred — distinguish this via state securities division
records.

### Step 4 Stored Output
```json
{
  "is_public_company": "boolean",
  "filings": [
    {
      "form_type":   "string  — e.g. 'Form D', '8-K'",
      "date":        "string  — YYYY-MM-DD",
      "description": "string  — summary of filing content",
      "url":         "string  — direct EDGAR link",
      "signal":      "string  — what this means for the investigation"
    }
  ],
  "gap": "boolean — true if EDGAR search failed or returned 403"
}
```

---

## 6. Step 5 — CourtListener Litigation

### Authentication
CourtListener MCP tools require authentication. Check `mcp-needs-auth-cache.json`
in the Claude settings directory for current auth status.

### Data Sought
```
Federal district court dockets where entity appears as:
  - Defendant  → liability signal; note case type
  - Plaintiff  → sometimes informative (serial IP litigation, debt collection)
```

### CourtListener Entity Schema (returned per docket)
```json
{
  "case_name":    "string  — e.g. 'EMONYON et al v. YREFY, LLC et al'",
  "docket_number":"string  — e.g. '1:25-cv-04586'",
  "court":        "string  — e.g. 'District of New Jersey'",
  "judge":        "string  — assigned judge name",
  "date_filed":   "string  — YYYY-MM-DD",
  "date_terminated": "string | null — YYYY-MM-DD if closed",
  "cause":        "string  — e.g. 'Breach of Contract'",
  "nature_of_suit": "string — numeric code + description",
  "party_roles":  [
    {
      "name": "string",
      "role": "plaintiff | defendant | interested_party"
    }
  ],
  "docket_entries": [
    {
      "date":        "string — YYYY-MM-DD",
      "description": "string — plain text docket entry"
    }
  ]
}
```

### Step 5 Stored Output
```json
{
  "cases": [
    {
      "case_name":     "string",
      "docket_number": "string",
      "court":         "string",
      "judge":         "string",
      "date_filed":    "string",
      "status":        "open | closed | unknown",
      "entity_role":   "plaintiff | defendant",
      "claim_types":   ["string"],
      "latest_activity": "string — YYYY-MM-DD"
    }
  ],
  "gap": "boolean — true if CourtListener auth was not available"
}
```

**Distinguish:** Entity sued vs. entity suing. Both are signals but of
different risk types. A company that sues frequently is different from
one that gets sued frequently.

---

## 7. Step 6 — Enigma Deep-Dive

### Authentication
Enigma requires an API key configured in the Enigma MCP server settings.
All sub-steps (6a–6g) are independent and should run in parallel.

---

### 7a. `enigma.search_business`

**Purpose:** Get the Enigma brand ID (required for 6e, 6f, 6g) and a
top-level firmographic snapshot.

**Input:**
```json
{
  "query":  "string  — specific business name or website",
  "limit":  "int     — number of results to return (use 3 to catch name variants)",
  "state":  "string? — optional state filter",
  "city":   "string? — optional city filter"
}
```

**Output — Brand Record:**
```json
{
  "brand_id":          "string  — Enigma internal brand identifier",
  "brand_name":        "string",
  "website":           "string",
  "naics_code":        "string  — 6-digit NAICS industry code",
  "naics_description": "string  — human-readable industry",
  "employee_count":    "number | null",
  "annual_revenue":    "number | null — estimated USD",
  "location_count":    "number",
  "payment_processors":["string — e.g. 'Stripe', 'Square'"],
  "ecommerce_platforms":["string"],
  "sample_addresses":  [
    {
      "street":  "string",
      "city":    "string",
      "state":   "string",
      "zip":     "string"
    }
  ]
}
```

**Key use:** `brand_id` is the foreign key that unlocks 6e (`get_brand_legal_entities`),
6f (`get_brand_card_analytics`), and 6g (`get_brands_by_legal_entity`).
Without it, those three tools cannot run.

**Failure mode:** If the entity is too small, too new, or operates under
a name Enigma doesn't index directly, `search_business` may return zero
results or a fuzzy match. Record this as a partial coverage gap — the
other Enigma sub-steps (6b, 6c, 6d) do not require `brand_id`.

---

### 7b. `enigma.search_kyb`

**Purpose:** Know-Your-Business verification — cross-checks the entity
name and address against government registry data and returns a
pass/fail/partial for each verification dimension.

**Input:**
```json
{
  "name":             "string  — business legal name",
  "state":            "string? — state abbreviation",
  "city":             "string? — city name",
  "street_address1":  "string? — street address",
  "postal_code":      "string? — ZIP code",
  "tin":              "string? — 9-digit EIN (requires add-on service)"
}
```

**Output — KYB Result:**
```json
{
  "risk_summary": {
    "tasks": [
      {
        "task_name": "string — e.g. 'name_verification' | 'address_verification' | 'sos_address_verification'",
        "status":    "string — 'success' | 'failure' | 'partial'",
        "result":    "string — e.g. 'name_exact_match' | 'address_not_verified'",
        "reason":    "string — explanation of pass/fail",
        "sources": [
          {
            "name":               "string  — matched entity name",
            "match_entity_type":  "string  — 'registered_entity' | 'dba' | ...",
            "urls":               ["string — source data URLs"]
          }
        ]
      }
    ]
  }
}
```

**Task names and what they check:**
```
name_verification         Name match against any Enigma government record
sos_address_verification  Address match against Secretary of State filing
address_verification      Address match against any Enigma record
tin_verification          EIN check against IRS data (requires add-on)
```

**Interpretation signals:**
- `name_exact_match` + `address_not_verified` → name is registered but
  address on file differs — possible registered agent / stale address
- `name_not_found` → entity not in Enigma's registry sweep; check if newly
  formed or operating under a DBA
- `success` on all tasks → strong identity confirmation

---

### 7c. `enigma.search_gov_archive`

**Purpose:** Broad sweep across 100+ government datasets — SOS registrations,
worker's comp filings, liquor licenses, SEC Form D, beneficial owner registries,
and more. The most complete cross-jurisdictional entity footprint available.

**Input:**
```json
{
  "query":            "string  — business name and/or address",
  "original_prompt":  "string? — context for the search (recommended)",
  "historical_data":  "boolean — true to include non-current records",
  "category":         "string  — 'all' | specific category filter",
  "limit":            "int     — records per page (max 300)",
  "page":             "int     — pagination",
  "include_row_details": "boolean — false for first pass, true for detail retrieval",
  "resource_ids":     ["string? — specific dataset IDs to target in second pass"]
}
```

**Output — Archive Hit:**
```json
{
  "hits": [
    {
      "dataset_info": {
        "resource_id":        "string  — Enigma dataset UUID",
        "dataset_title":      "string  — e.g. 'Active Iowa Business Entities'",
        "dataset_organization":"string  — e.g. 'State of Iowa'",
        "last_updated_at":    "number  — Unix timestamp",
        "is_current":         "boolean"
      },
      "matched_row_info": {
        "business_name":  "string",
        "city":           "string",
        "state":          "string",
        "zip_code":       "string",
        "street_address": "string"
      },
      "row_details": { }
    }
  ],
  "total_found": "number",
  "page":        "number",
  "metadata": {
    "records_per_page":        "number",
    "records_returned":        "number",
    "historical_data":         "boolean",
    "filtered_out_non_current":"number"
  }
}
```

**Two-pass strategy:**
1. **Pass 1** — `include_row_details=false`, `historical_data=true`. Identify
   which `resource_id` values are most valuable (e.g. SEC Form D dataset ID
   `95bc2b3a-...`, DC Beneficial Owners ID `70308a2e-...`).
2. **Pass 2** — `include_row_details=true`, `resource_ids=[high_value_ids]`.
   Pull full row-level data from those specific datasets only.

**High-value dataset resource IDs encountered in practice:**
```
95bc2b3a-24b8-4daf-aa6d-c1f8d56d87a3  SEC Form D Data Sets
70308a2e-f687-43d5-b998-a0b0f42df404  DC Beneficial Owners
bfe829dc-bf61-49b7-a73d-8473bdd39291  Connecticut Business Registry
d49c853b-f873-4203-a9fe-296f5af71eae  Florida Sunbiz Quarterly
351da7f8-1782-4c71-a552-8eec0e3ad377  DC Open Data Portal Business Datasets
```

**What to look for in the archive sweep:**
- **Suite number differences** between entity registrations (e.g. SLP4 in
  Suite 130, SLP5 in Suite 210) — signals operational separation of fund vehicles
- **State registration footprint** — which states each entity is registered in
  reveals where it is actively fundraising or operating
- **Numbered fund series** (SLP1, SLP2, SLP3...) — map the full sequence and
  flag any gaps (a missing SLP2 may indicate a failed or unregistered fund)
- **`is_current: false` records** — historical registrations that are now
  inactive reveal past operating history, former addresses, or dissolved entities
- **DC Beneficial Owners registry** — despite the name, this dataset contains
  corporate registration data, not individual beneficial owner names; note as gap

---

### 7d. `enigma.search_negative_news`

**Purpose:** AI-powered adverse media sweep, broader than GDELT because it
is not limited to a 3-month lookback window and searches structured databases
in addition to news.

**Input:**
```json
{
  "business_name": "string  — legal name of the business",
  "address":       "string  — full HQ address to disambiguate from same-name entities"
}
```

**Output — Negative News Record:**
```json
{
  "risk_assessment": {
    "level":       "string  — 'high' | 'medium' | 'low' | 'unknown'",
    "explanation": "string  — narrative summary of why this risk level was assigned"
  },
  "findings": [
    "string — each finding is a free-text sentence with inline citation markers like [1]"
  ],
  "sources": [
    "string — URLs corresponding to the citation markers in findings[]"
  ]
}
```

**Risk level definitions:**
```
high     Multiple documented regulatory, legal, or financial issues
medium   Some adverse findings but limited in scope or recency
low      Minor issues or historical only
unknown  Insufficient public information to assess
```

**Processing:** Each finding string must be parsed for:
1. The factual claim (store in `known_facts` or `allegations` depending on
   whether it is adjudicated)
2. The source citation number (map to the `sources[]` array)
3. Whether it duplicates a finding from Steps 2, 4, or 5 (deduplicate)

**Important:** `search_negative_news` results often include both confirmed
regulatory actions AND unverified allegations in the same `findings[]` array.
You must separate these before adding to the internal model. Adjudicated
findings (consent orders, court judgments) go to `known_facts`. Unverified
claims (investigative pieces, social media, plaintiff allegations) go to
`allegations`.

---

### 7e. `enigma.get_brand_legal_entities`

**Purpose:** Given a `brand_id` from Step 6a, pull all legal entities
(LLCs, corps, DBAs) associated with that brand across all state registries.

**Input:**
```json
{ "brand_id": "string" }
```

**Output — Legal Entity Record:**
```json
{
  "result": "string — human-readable summary containing structured data",
  "entities": [
    {
      "entity_name":     "string",
      "entity_type":     "string  — 'Corporation' | 'LLC' | 'Limited Liability Company' | ...",
      "formation_date":  "string  — YYYY-MM-DD",
      "enigma_id":       "string  — Enigma internal entity UUID",
      "registrations": [
        {
          "state":       "string  — state name or abbreviation",
          "file_number": "string",
          "issued_date": "string  — YYYY-MM-DD",
          "status":      "string  — 'active' | 'inactive' | 'dissolved'",
          "entity_type_desc": "string",
          "addresses":   ["string — full address strings"],
          "key_personnel": [
            {
              "role":   "string  — 'Director' | 'Registered Agent' | 'Manager' | 'Organizer'",
              "name":   "string"
            }
          ]
        }
      ],
      "registration_summary": {
        "domestic_states":          "number",
        "active_registrations":     "number"
      }
    }
  ]
}
```

**Key signals:**
- `key_personnel[].name` — individuals named as directors, managers, or registered
  agents are leads for Step 8's entity graph; run `enigma.search_person` or
  `opensanctions.match_entity` (schema="Person") on them
- Multiple `registrations[]` across states = multi-state fundraising or operations
- `status: 'inactive'` or `'dissolved'` on a registration = entity pulled back from
  that jurisdiction (possible regulatory bar or voluntary exit)
- Address mismatches between registrations and the claimed HQ = flag for investigation

---

### 7f. `enigma.get_brand_card_analytics`

**Purpose:** Transaction-level financial analytics from aggregated payment
processor data (Square, Stripe, Toast, etc.). Use when financial health or
business trajectory is relevant.

**Input:**
```json
{
  "brand_id":       "string",
  "months_back":    "int?  — default 12, max 60; only specify if user requested a timeframe",
  "original_prompt":"string? — context"
}
```

**Output — Card Analytics Record:**
```json
{
  "brand_name":              "string",
  "annual_revenue_estimate": "number | null — USD",
  "yoy_revenue_growth":      "number | null — percentage",
  "avg_daily_customers":     "number | null",
  "total_transactions":      "number | null",
  "avg_transaction_size":    "number | null — USD",
  "refund_rate":             "number | null — percentage",
  "monthly_breakdown": [
    {
      "month":              "string  — YYYY-MM",
      "revenue":            "number | null",
      "revenue_growth_yoy": "number | null",
      "daily_customers":    "number | null",
      "transaction_count":  "number | null",
      "avg_transaction":    "number | null",
      "refunds":            "number | null"
    }
  ]
}
```

**Investigation signals:**
- Sudden revenue decline + continued fundraising = potential liquidity stress
- High refund rate = product/service dissatisfaction or chargebacks
- Revenue growth not matching claimed investor returns = possible discrepancy
  to investigate (e.g. claiming 2% portfolio default rate but revenue declining)
- Note: card analytics cover consumer-facing transactions only; a B2B or
  investor-facing company like Yrefy may have low card volume but high wire
  transfer volume (not captured here)

---

### 7g. `enigma.get_brands_by_legal_entity`

**Purpose:** Reverse lookup — given a legal entity ID, find all brands
operating under it. Used when 6e surfaces a parent/holding entity.

**Input:**
```json
{ "legal_entity_id": "string — Enigma UUID from get_brand_legal_entities" }
```

**Output:**
```json
{
  "brands": [
    {
      "brand_id":           "string",
      "brand_name":         "string",
      "industry":           "string",
      "description":        "string",
      "location_count":     "number",
      "website":            "string"
    }
  ]
}
```

**Use case:** If the target company's legal entity is shared with other brands
you weren't previously aware of, those brands become new investigation threads.
Shared-entity patterns across seemingly unrelated businesses can reveal beneficial
ownership structures that aren't apparent from the company name alone.

---

### Step 6 Stored Output (combined)
```json
{
  "brand": {
    "brand_id":          "string | null",
    "name":              "string",
    "naics":             "string",
    "employee_count":    "number | null",
    "revenue_estimate":  "number | null"
  },
  "kyb": {
    "name_verified":     "boolean",
    "address_verified":  "boolean",
    "tasks":             []
  },
  "gov_archive": {
    "datasets_hit":      ["string — dataset titles where entity appeared"],
    "states_registered": ["string — state names"],
    "entities_found":    ["string — all legal entity names found"],
    "fund_series":       ["string — numbered fund entities in order, e.g. ['SLP1','SLP3']"],
    "fund_gaps":         ["string — sequence gaps, e.g. ['SLP2']"],
    "suite_variants":    ["string — distinct suite numbers observed"]
  },
  "negative_news": {
    "risk_level":  "string",
    "findings":    [],
    "sources":     []
  },
  "legal_entities": [
    {
      "name":         "string",
      "type":         "string",
      "formed":       "string",
      "states":       ["string"],
      "personnel":    [{"role": "string", "name": "string"}],
      "status":       "string"
    }
  ],
  "card_analytics": { } ,
  "related_brands":  []
}
```

---

## 8. Step 7 — Internal Data Model

This is the normalized, deduplicated representation built before any HTML
is written. All upstream data flows into this model. The HTML report is a
rendering of this model — nothing appears in the report that isn't in the model.

### 8a. ENTITY LIST

Every named entity in the investigation, including the primary subject,
subsidiaries, individuals, regulators, and external parties.

```json
{
  "entities": [
    {
      "id":           "string  — short slug, e.g. 'yrefy-llc'",
      "display_name": "string  — as it appears in the report",
      "legal_name":   "string  — full legal name",
      "type":         "company | person | regulator | fund | plaintiff | endorser | investigator",
      "role":         "string  — free-text role description, e.g. 'Operating company'",
      "status":       "active | inactive | dissolved | unknown",
      "address":      "string | null",
      "formed":       "string | null  — YYYY-MM-DD or YYYY",
      "jurisdiction": "string | null",
      "relationships": [
        {
          "target_id":   "string  — id of the related entity",
          "type":        "string  — 'controls' | 'leads' | 'founded' | 'endorses' | 'regulates' | 'sues' | 'investigates'",
          "direction":   "from_this | to_this | bidirectional",
          "description": "string  — short label for graph edge",
          "confirmed":   "boolean — false if relationship is alleged only"
        }
      ],
      "sources":      ["string — footnote numbers where this entity is documented"],
      "graph": {
        "color":      "string  — hex color per type (see HTML schema section)",
        "x":          "number  — SVG x position, assigned at render time",
        "y":          "number  — SVG y position, assigned at render time",
        "radius":     "number  — node radius (primary entity = 38, secondary = 28, tertiary = 22)"
      }
    }
  ]
}
```

**Entity type → graph color mapping:**
```
company     → #27ae60  (green)
fund        → #2ecc71  (light green, dashed border if historical)
regulator   → #3498db  (blue)
plaintiff   → #e67e22  (orange)
person      → #9b59b6  (purple)
endorser    → #95a5a6  (gray)
investigator→ #c0392b  (red, dashed border)
enforcement → #e74c3c  (bright red)
```

---

### 8b. TIMELINE

Ordered list of all dated events extracted from all sources.

```json
{
  "timeline": [
    {
      "date":         "string  — YYYY-MM-DD or YYYY or 'YYYY-MM'",
      "date_precision":"day | month | year | approximate",
      "title":        "string  — short headline (≤ 80 chars)",
      "body":         "string  — 1–3 sentence description with inline footnotes",
      "event_type":   "founding | filing | action | lawsuit | media | statement",
      "entities":     ["string — entity IDs involved"],
      "sources":      ["string — footnote numbers"],
      "is_major":     "boolean — true for events that get a special callout in the report"
    }
  ]
}
```

**Event type → timeline dot color:**
```
founding   → #27ae60  green
filing     → #3498db  blue
action     → #e74c3c  red (with glow — CSS box-shadow)
lawsuit    → #e67e22  orange
media      → #9b59b6  purple
statement  → #95a5a6  gray
```

**Sorting rule:** Ascending by `date`. For approximate dates (year-only),
place at the start of that year (Jan 1). For `~` approximations, note
`date_precision: "approximate"` and add a tilde in the display date.

---

### 8c. KNOWN FACTS

Verified, source-cited facts only. No allegations. No unconfirmed claims.

```json
{
  "known_facts": [
    {
      "field":    "string  — label, e.g. 'Legal name'",
      "value":    "string  — the fact",
      "sources":  ["string — footnote numbers"],
      "category": "identity | structure | financials | regulatory | litigation | operations"
    }
  ]
}
```

**Category definitions:**
```
identity     Legal name, aliases, jurisdiction, formation date, HQ address
structure    Ownership, subsidiaries, fund entities, registered agents
financials   Revenue, capital raised, employee count, investment terms
regulatory   Licenses, registrations, enforcement actions, consent orders
litigation   Active and closed lawsuits, docket numbers, parties
operations   Business model, geography, products, excluded states
```

---

### 8d. ALLEGATIONS

Unverified claims — from investigative sources, plaintiffs, social media,
or other unresolved parties.

```json
{
  "allegations": [
    {
      "claim":        "string  — statement of the allegation",
      "source_name":  "string  — e.g. 'Barry Minkow, Substack'",
      "source_url":   "string",
      "date":         "string  — YYYY-MM-DD when published",
      "credibility_note": "string | null — e.g. source is a convicted fraudster",
      "status":       "unverified | refuted | partially_confirmed | adjudicated",
      "footnote":     "string  — footnote number"
    }
  ]
}
```

**Status definitions:**
```
unverified          No independent confirmation; should not be treated as fact
refuted             The claim has been shown to be false (note the basis)
partially_confirmed Some elements confirmed by independent sources
adjudicated         A court or regulator has ruled on this (move to known_facts)
```

Note: even `adjudicated` findings where the respondent "neither admits nor
denies" (common in SEC/state securities consent orders) should remain in this
section if the underlying facts are disputed, and be cross-referenced to
the known_facts entry for the penalty/outcome.

---

### 8e. KEY LEADS

Actionable investigative follow-ups, sorted by priority.

```json
{
  "key_leads": [
    {
      "title":       "string  — ≤ 60 char headline",
      "priority":    "high | medium | low",
      "description": "string  — what to do, where to look, why it matters",
      "source_gaps": ["string — coverage gap IDs this lead would close"],
      "entities":    ["string — entity IDs relevant to this lead"]
    }
  ]
}
```

**Priority criteria:**
```
high    Would materially change the risk assessment if resolved;
        document is known to exist and is obtainable
medium  Significant but requires more effort or may not be accessible
low     Nice-to-have context; unlikely to change core findings
```

---

### 8f. COVERAGE GAPS

Every source checked, not just the ones that failed. Absence of a hit
is itself a finding.

```json
{
  "coverage_gaps": [
    {
      "source":      "string  — tool or data source name",
      "status":      "checked_clean | rate_limited | auth_required | http_error | not_run | partial",
      "detail":      "string  — what happened and what it means for coverage",
      "substituted": "boolean — true if another source was used as a proxy"
    }
  ]
}
```

**Status definitions:**
```
checked_clean   Tool ran successfully and returned no adverse findings
rate_limited    Tool throttled the request (e.g. GDELT 429)
auth_required   Tool needs authentication that was not available
http_error      Non-auth HTTP error (403, 500, etc.)
not_run         Tool was available but this source was not applicable
partial         Tool ran but returned incomplete data (e.g. entity status but not owner names)
```

---

## 9. Step 8 — HTML Report Schema

### File
```
Filename:  [CompanyName]-intelligence-[YYYY-MM-DD].html
Location:  User's Desktop (fallback: current working directory)
Encoding:  UTF-8
Dependencies: None (fully self-contained; all CSS and JS inline)
```

### Document Structure
```
<html>
  <head>
    <style>          ← All CSS inline; no external stylesheets
  <body>
    <div.container>
      ├── div.report-header       ← Company name, risk badge, meta, print button
      ├── h2 + table.facts        ← known_facts[] rendered as table rows
      ├── h2 + div.timeline       ← timeline[] rendered as .tl-item list
      ├── h2 + div.graph-wrap     ← SVG entity network + legend
      ├── h2 + div.lead-item*     ← key_leads[] rendered as cards
      ├── h2 + div.allegation-box*← allegations[] rendered as boxed items
      ├── h2 + table.gap-table    ← coverage_gaps[] rendered as table
      └── div.footnotes           ← numbered source list
```

### CSS Class → Data Model Mapping
```
.report-header         ← target.legal_name, risk_level, investigation date
.risk-badge.risk-high  ← negative_news.risk_level == "high"
.risk-badge.risk-medium← negative_news.risk_level == "medium"
.risk-badge.risk-low   ← negative_news.risk_level == "low"

table (facts)          ← known_facts[], one <tr> per fact
  td:first-child       ← known_fact.field
  td:nth-child(2)      ← known_fact.value
  td:last-child <sup> ← known_fact.sources[]

div.timeline           ← timeline[], chronological order
  div.tl-item          ← one per timeline event
    div.tl-dot.founding  ← event_type == "founding"
    div.tl-dot.filing    ← event_type == "filing"
    div.tl-dot.action    ← event_type == "action"
    div.tl-dot.lawsuit   ← event_type == "lawsuit"
    div.tl-dot.media     ← event_type == "media"
    div.tl-date          ← timeline_event.date (display form)
    div.tl-title         ← timeline_event.title
    div.tl-body          ← timeline_event.body (with <sup> footnotes)

svg#network-graph      ← entities[] and their relationships[]
  <circle>             ← one per entity, colored by entity.type
  <text>               ← entity.display_name, below circle
  <line>               ← one per relationship, from entity to target
  <text> on line       ← relationship.description
  <marker#arrow>       ← arrowhead terminus

div.lead-item          ← one per key_leads[] entry
  div.lead-priority    ← lead.priority ("HIGH PRIORITY" / "MEDIUM PRIORITY")
  div.lead-title       ← lead.title
  div.lead-body        ← lead.description

div.allegation-box     ← one per allegations[] entry
  div.allegation-label ← "Unverified — source: [source_name]"
  (body text)          ← allegation.claim + credibility_note

table.gap-table        ← coverage_gaps[], one <tr> per source
  td.gap-ok            ← status == "checked_clean"
  td.gap-miss          ← status in ["rate_limited","auth_required","http_error","not_run"]
  td.gap-partial       ← status == "partial"

div.footnotes          ← flat numbered list matching all <sup>[N]</sup> in document
  span.fn-num          ← footnote number
  <a href>             ← source URL
```

### SVG Network Graph Layout Rules
```
ViewBox:    0 0 900 450
Center:     Primary entity at approximately (450, 210)

Node radius by tier:
  Primary (target company)  r = 38
  Secondary (subsidiaries, key individuals, regulators) r = 26–30
  Tertiary (endorsers, plaintiffs, external) r = 22

Spatial clustering:
  Leadership (persons)      upper-left quadrant
  Endorsers / external      left edge
  Primary entity            center
  Subsidiary funds          lower-center row
  Regulators                upper-right quadrant
  Plaintiffs / litigants    lower-right quadrant
  Investigators / critics   upper-center

Edge style by relationship confirmed status:
  confirmed = true          stroke solid, opacity 0.7, marker-end arrow
  confirmed = false         stroke-dasharray="4,3", opacity 0.4

Edge color by relationship type:
  controls / manages        #3a3a5a  (dark blue-gray)
  leads / founded           #444     (dark gray)
  endorses (paid)           #444 + stroke-dasharray (dashed)
  regulates                 #3498db55 (translucent blue)
  enforcement / order       #c0392b66 (translucent red)
  sues / litigates          #e67e2299 (translucent orange)
  investigates              #c0392b55 + stroke-dasharray (red dashed)

Text labels:
  Max 20 chars per line; use <tspan> for two-line labels
  Font: 'Georgia', serif; size: 9–11px
  Color: #e0e0e0 on dark fill nodes; #aaa on inactive/historical nodes
  Positioned below circle with dy offset based on radius
```

---

## 10. Field Vocabulary

Controlled vocabulary for fields used across the internal data model:

| Field | Allowed Values |
|---|---|
| `entity.type` | `company` `fund` `person` `regulator` `plaintiff` `endorser` `investigator` |
| `entity.status` | `active` `inactive` `dissolved` `unknown` |
| `relationship.type` | `controls` `leads` `founded` `endorses` `regulates` `sues` `investigates` `associated` |
| `relationship.direction` | `from_this` `to_this` `bidirectional` |
| `timeline.event_type` | `founding` `filing` `action` `lawsuit` `media` `statement` |
| `timeline.date_precision` | `day` `month` `year` `approximate` |
| `known_fact.category` | `identity` `structure` `financials` `regulatory` `litigation` `operations` |
| `allegation.status` | `unverified` `refuted` `partially_confirmed` `adjudicated` |
| `lead.priority` | `high` `medium` `low` |
| `coverage_gap.status` | `checked_clean` `rate_limited` `auth_required` `http_error` `not_run` `partial` |
| `opensanctions.topic` | `sanction` `sanction.linked` `role.pep` `role.rca` `crime` `crime.fin` `crime.fraud` `debarment` `export.control` |
| `html.risk_badge` | `risk-high` `risk-medium` `risk-low` |

---

## 11. Coverage Gap Taxonomy

When a source cannot be checked, the gap must be classified so readers
understand what the absence means for the overall risk assessment.

| Gap Type | Cause | Meaning for Report |
|---|---|---|
| `rate_limited` | Tool throttled (HTTP 429) | Data exists but wasn't retrieved this run; retry later |
| `auth_required` | MCP server needs login | Source cannot be checked without first authenticating |
| `http_error` | Non-auth server error | May be temporary; note the specific error code |
| `not_run` | Source not applicable | e.g. EDGAR not relevant for non-US entity; this is a judgment call, not a failure |
| `partial` | Tool ran but returned incomplete data | What was returned and what was missing must both be described |
| `checked_clean` | Tool ran successfully, zero hits | Explicitly state this is a clean result, not a gap |

**A `checked_clean` result is not a gap** — it is a finding. Omitting it
from the coverage section would make the report appear to have less coverage
than it actually does. Always report all sources checked, regardless of outcome.

**Never omit a gap.** A gap that is not reported makes the report look more
complete than it is, which is worse than surfacing the limitation. A reader
who acts on a report believing it covered PACER when it did not could miss
active federal litigation entirely.
