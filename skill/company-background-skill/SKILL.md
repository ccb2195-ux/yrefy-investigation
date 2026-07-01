---
name: company-background-investigation
description: Runs a structured public-records background investigation on a company or executive by combining adverse news search (GDELT), sanctions/PEP/watchlist screening (OpenSanctions), SEC filings (EDGAR), and litigation history (CourtListener). Use this whenever the user asks to "background," "investigate," "screen," "do due diligence on," or "check for red flags on" a company, business, or person, or asks for a "risk profile" / "KYB check" / "adverse media search." Also trigger for vaguer requests like "what can you find on this company" or "any lawsuits or sanctions on X." Prefer this over an ad-hoc web search when the user wants a systematic, multi-source investigation rather than a single quick fact.
---

# Company Background Investigation

A repeatable workflow for investigating a company or individual across public
records: adverse news, sanctions/PEP watchlists, financial filings, and
litigation. Produces a structured risk profile with citations back to
primary sources.

## When to use this

Trigger on requests like:
- "Background [Company] for me"
- "Do a due diligence check on [Company/Person]"
- "Any red flags on [Company]?"
- "Check [Company] against sanctions lists"
- "What's [Company]'s litigation history?"
- "Give me a risk profile on [Company]"

Do NOT use this for simple lookups that don't need multi-source
investigation (e.g. "what does Acme Corp make" -- just answer or web search
directly). This skill is for when the user wants a *systematic* sweep.

## Available tools

This skill assumes the following MCP servers/tools are connected. If any are
missing, tell the user which one and proceed with what's available rather
than failing outright.

| Tool | Source | Purpose | Auth needed |
|---|---|---|---|
| `gdelt.search_news` | GDELT DOC 2.0 API | Adverse media / news mentions | None |
| `gdelt.search_news_tone` | GDELT DOC 2.0 API | Sentiment timeline (spot scandal windows) | None |
| `opensanctions.search_entity` | OpenSanctions | Sanctions/PEP/watchlist free-text search | Free API key |
| `opensanctions.match_entity` | OpenSanctions | Higher-precision fuzzy screening | Free API key |
| `opensanctions.get_entity` | OpenSanctions | Full record incl. relationships | Free API key |
| CourtListener MCP tools | CourtListener | Federal litigation & dockets | Varies |
| Enigma MCP tools (if connected) | Enigma | KYB / firmographics / ownership graph | API key |
| `web_search` / EDGAR fetch | SEC EDGAR full-text search | Public filings, insider trades | None |

## Workflow

Run these steps in order. Don't skip steps silently -- if a step returns
nothing or a tool is unavailable, say so explicitly in the final report
rather than omitting the section.

### Step 1: Clarify the target
Confirm the exact legal name and, if possible, jurisdiction/HQ location and
any known aliases or subsidiaries. Ambiguous names ("Phoenix Holdings") need
disambiguation before screening -- a wrong-entity match is worse than no
match. If the user hasn't specified, ask once, or proceed with the most
likely candidate and flag the assumption.

### Step 2: Adverse media search (GDELT)
Call `gdelt.search_news` with the entity name in quotes, `timespan="3months"`
first (broadest free lookback for full-text search). If results are sparse,
retry with a shorter timespan and broader terms, or add known aliases.

Optionally call `gdelt.search_news_tone` to find windows of unusually
negative coverage, then re-run `search_news` narrowed to that window (GDELT's
`timespan` also accepts explicit date ranges) to find the specific articles
driving the negative tone.

Note: GDELT's free full-text search only covers roughly the last 3 months.
For older adverse media, rely on web_search and cite what's found there
instead.

### Step 3: Sanctions / PEP / watchlist screening (OpenSanctions)
Call `opensanctions.match_entity` with the entity's legal name and schema
("Company" or "Person"). This is preferred over `search_entity` for
screening because it returns confidence-scored matches designed for exactly
this use case.

For any match with a non-trivial score, call `opensanctions.get_entity` on
the matched ID to pull the full record, including ownership/family/associate
relationships -- this is often where the most useful signal is (e.g. a
company isn't sanctioned itself, but its listed owner is).

Report topics found (sanction, sanction.linked, role.pep, crime, debarment,
etc.) plainly -- don't editorialize about guilt. A PEP match is not an
accusation; it's a disclosure requirement flag.

### Step 4: Financial filings (SEC EDGAR)
If the entity could plausibly be a US public company or subsidiary of one,
search EDGAR's full-text search (https://www.sec.gov/cgi-bin/browse-edgar or
the full-text search UI at https://efts.sec.gov/LATEST/search-index?q=...)
for the entity name. Look specifically for:
- 8-K filings (material events -- litigation, investigations, restatements)
- Litigation releases and AAERs (accounting/auditing enforcement)
- Form 4 insider trading clusters around notable dates found in Step 2

If EDGAR isn't a fit (private company, non-US), say so and move on rather
than forcing a search.

### Step 5: Litigation history (CourtListener)
Use the connected CourtListener tools to search for federal dockets naming
the entity as plaintiff or defendant. Distinguish between the entity being
sued (potential liability signal) and the entity suing others (sometimes
itself informative, e.g. serial IP litigation).

### Step 6: Corporate structure / ownership (Enigma deep-dive)

Run all applicable Enigma tools in parallel. If Enigma is not connected,
note it as a coverage gap and skip. Do not run these sequentially -- they
are independent and should fire at the same time.

**6a. search_business(query=entity_name, limit=3)**
Get the brand ID and top-level firmographic profile: revenue, NAICS, employee
count, tech stack, location count. If multiple results return, pick the
closest match and flag the assumption.

**6b. search_kyb(name=entity_name, state=state, city=city)**
KYB verification: name match against government records, address verification,
SOS filings. Note which verification tasks pass/fail and why.

**6c. search_gov_archive(query=entity_name, historical_data=True)**
Sweep government databases -- business registrations, licenses, worker's comp
filings, SEC Form D data, state SOS records. This surfaces subsidiary entities,
multi-state registration footprints, and historical names. If the initial pass
reveals high-value dataset resource_ids (e.g. SEC Form D, DC Beneficial
Owners), do a second pass with include_row_details=True on those specific IDs.

**6d. search_negative_news(business_name=entity_name, address=hq_address)**
AI-powered adverse news sweep. This often surfaces allegations, regulatory
actions, and reputational risks beyond what GDELT returns. Cross-check findings
against Steps 2-5 to confirm or extend.

**6e. get_brand_legal_entities(brand_id=...)**
Pull all legal entities (LLCs, corps, DBAs) associated with the brand.
Look for: multiple SOS registrations, foreign filings, holding company
patterns, gaps in expected jurisdictions.

**6f. get_brand_card_analytics(brand_id=...) [optional]**
Pull transaction-level financial analytics (revenue trend, YoY growth,
refund rate). Use when financial health or business trajectory is relevant
to the investigation. Omit for purely legal/ownership questions.

**6g. get_brands_by_legal_entity(legal_entity_id=...) [optional]**
If Step 6e surfaces a holding company or parent entity, reverse-lookup to
find all other brands tied to the same legal entity. Useful for uncovering
sister companies or shared-officer networks.

After running 6a–6g, synthesize:
- How many distinct legal entities exist and in which states?
- Do the registered addresses match the claimed HQ?
- Are there suite-number differences between entities (potential operational
  separation)?
- Does the SEC Form D archive show a numbered fund series (SLP1, SLP2...)?
  If so, map the sequence and flag any gaps.
- Do beneficial owner records surface individual names? If not, note as gap.

### Step 7: Synthesize findings across all sources

Before writing the HTML report, build an internal data model:

**ENTITY LIST** — every legal entity, individual, regulator, and external party
identified, with their role and relationship to the target.

**TIMELINE** — ordered list of dated events extracted from all sources:
formation dates, fund launches, regulatory filings, enforcement actions,
lawsuits, media events, notable statements. Mark each event with a source
footnote number.

**KNOWN FACTS** — verified, source-cited facts only. Separate from allegations.
Include: legal name, HQ, formation date, capital raised, employee count,
regulatory status, confirmed penalties, confirmed litigation.

**ALLEGATIONS / UNVERIFIED** — claims from investigative sources, social media,
or plaintiffs that have not been adjudicated. Clearly label each as unverified.

**KEY LEADS** — gaps that a journalist or investigator should pursue next:
unobtained documents, unnamed individuals, unresolved filings, state agencies
not yet contacted, time windows with missing data.

**COVERAGE GAPS** — tools that returned no data or errored, and whether absence
of a hit is meaningful.

### Step 8: Generate the HTML intelligence report

Write a self-contained HTML file to the user's Desktop (or current working
directory if Desktop is unavailable) named
`[CompanyName]-intelligence-[YYYY-MM-DD].html`.

The file must be fully self-contained -- no external CDN dependencies. All
CSS and JavaScript must be inline. Use only standard browser APIs.

Use the following structure and style guidelines:

---

**HTML TEMPLATE STRUCTURE:**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>[Company] — Intelligence Report [DATE]</title>
  <style>
    /* Dark investigative theme */
    body { font-family: 'Georgia', serif; background: #0f1117; color: #e0e0e0;
           margin: 0; padding: 0; }
    .container { max-width: 1100px; margin: 0 auto; padding: 40px 24px; }

    /* Header */
    .report-header { border-bottom: 2px solid #c0392b; padding-bottom: 20px;
                     margin-bottom: 40px; }
    .report-header h1 { font-size: 2rem; color: #fff; margin: 0 0 6px; }
    .report-header .meta { color: #888; font-size: 0.85rem; }
    .risk-badge { display: inline-block; padding: 4px 12px; border-radius: 4px;
                  font-size: 0.75rem; font-weight: bold; text-transform: uppercase;
                  margin-left: 12px; }
    .risk-high { background: #c0392b; color: #fff; }
    .risk-medium { background: #e67e22; color: #fff; }
    .risk-low { background: #27ae60; color: #fff; }

    /* Section headers */
    h2 { color: #c0392b; font-size: 1.1rem; text-transform: uppercase;
         letter-spacing: 1px; border-bottom: 1px solid #2a2a3a;
         padding-bottom: 8px; margin-top: 48px; }

    /* Known facts table */
    table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
    th { text-align: left; padding: 8px 12px; background: #1a1a2e;
         color: #aaa; font-weight: normal; text-transform: uppercase;
         font-size: 0.75rem; letter-spacing: 0.5px; }
    td { padding: 8px 12px; border-bottom: 1px solid #1e1e2e; vertical-align: top; }
    tr:hover td { background: #1a1a2e; }

    /* Timeline */
    .timeline { position: relative; padding-left: 32px; }
    .timeline::before { content: ''; position: absolute; left: 8px; top: 0;
                        bottom: 0; width: 2px; background: #2a2a3a; }
    .tl-item { position: relative; margin-bottom: 24px; }
    .tl-dot { position: absolute; left: -28px; top: 4px; width: 12px; height: 12px;
              border-radius: 50%; background: #c0392b; border: 2px solid #0f1117; }
    .tl-dot.action { background: #e74c3c; box-shadow: 0 0 8px #e74c3c88; }
    .tl-dot.filing { background: #3498db; }
    .tl-dot.lawsuit { background: #e67e22; }
    .tl-dot.founding { background: #27ae60; }
    .tl-date { font-size: 0.75rem; color: #888; margin-bottom: 2px; }
    .tl-title { font-weight: bold; color: #e0e0e0; font-size: 0.95rem; }
    .tl-body { font-size: 0.85rem; color: #aaa; margin-top: 4px; line-height: 1.5; }

    /* Network graph */
    #network-graph { background: #0a0a14; border: 1px solid #2a2a3a;
                     border-radius: 8px; width: 100%; height: 480px;
                     overflow: visible; display: block; }
    .node-group text { font-family: 'Georgia', serif; }

    /* Leads */
    .lead-item { border-left: 3px solid #e67e22; padding: 10px 16px;
                 margin-bottom: 12px; background: #13131f; border-radius: 0 4px 4px 0; }
    .lead-item .lead-priority { font-size: 0.7rem; color: #e67e22;
                                text-transform: uppercase; font-weight: bold; }
    .lead-item .lead-title { font-weight: bold; margin: 4px 0; }
    .lead-item .lead-body { font-size: 0.85rem; color: #aaa; line-height: 1.5; }

    /* Allegations box */
    .allegation-box { background: #1a0f0f; border: 1px solid #5a1a1a;
                      border-radius: 4px; padding: 12px 16px; margin-bottom: 10px;
                      font-size: 0.85rem; color: #ccc; }
    .allegation-box .label { color: #e74c3c; font-size: 0.7rem;
                              text-transform: uppercase; font-weight: bold; }

    /* Footnotes */
    .footnotes { margin-top: 48px; padding-top: 16px; border-top: 1px solid #2a2a3a;
                 font-size: 0.78rem; color: #666; }
    .footnotes a { color: #5a7fbf; text-decoration: none; }
    .footnotes a:hover { text-decoration: underline; }
    sup { color: #5a7fbf; font-size: 0.7rem; cursor: default; }

    /* Coverage gaps */
    .gap-table td:first-child { color: #aaa; width: 220px; }
    .gap-ok { color: #27ae60; }
    .gap-miss { color: #e74c3c; }
    .gap-partial { color: #e67e22; }
  </style>
</head>
<body>
<div class="container">

  <!-- HEADER -->
  <div class="report-header">
    <h1>[COMPANY LEGAL NAME] <span class="risk-badge risk-high">HIGH RISK</span></h1>
    <div class="meta">
      Intelligence Report &nbsp;·&nbsp; [DATE] &nbsp;·&nbsp;
      Sources: Enigma · GDELT · OpenSanctions · SEC EDGAR · Web
    </div>
  </div>

  <!-- KNOWN FACTS -->
  <h2>Known Facts</h2>
  <table>
    <tr><th>Field</th><th>Value</th><th>Source</th></tr>
    <!-- One row per verified fact, e.g.: -->
    <tr><td>Legal name</td><td>Yrefy LLC</td><td><sup>[1]</sup></td></tr>
    <!-- ... -->
  </table>

  <!-- TIMELINE -->
  <h2>Timeline of Key Events</h2>
  <div class="timeline">
    <!-- One .tl-item per event. Use dot class: founding / filing / action / lawsuit -->
    <div class="tl-item">
      <div class="tl-dot founding"></div>
      <div class="tl-date">2017</div>
      <div class="tl-title">Company founded</div>
      <div class="tl-body">Yrefy LLC formed in Arizona by Donald Fenstermaker
        and Laine Schoneberger.<sup>[1]</sup></div>
    </div>
    <!-- ... more events ... -->
  </div>

  <!-- NETWORK GRAPH -->
  <h2>Entity Network</h2>
  <svg id="network-graph" viewBox="0 0 900 440">
    <defs>
      <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5"
              markerWidth="6" markerHeight="6" orient="auto">
        <path d="M 0 0 L 10 5 L 0 10 z" fill="#555"/>
      </marker>
    </defs>
    <!--
      INSTRUCTIONS FOR GRAPH GENERATION:
      - Place the primary entity (the company) near center.
      - Group nodes by role using color:
          #27ae60 = founding/operating entities (companies)
          #3498db = regulatory bodies / government
          #e67e22 = legal adversaries / plaintiffs
          #c0392b = enforcement actions / adverse events
          #9b59b6 = individuals (leadership, endorsers)
          #95a5a6 = external parties (media, investors)
      - Draw edges as <line> elements between node centers.
      - Label each edge with a short relationship descriptor in a <text> element.
      - Each node is a <circle r="28"> + <text> label below it.
      - Scale node positions to fit within the 900x440 viewBox.
      - Example node:
          <g class="node-group" transform="translate(450,220)">
            <circle r="32" fill="#27ae60" stroke="#0f1117" stroke-width="3"/>
            <text text-anchor="middle" dy="48" fill="#e0e0e0" font-size="11">
              Yrefy LLC
            </text>
          </g>
      - Example edge (from center node at 450,220 to a node at 200,100):
          <line x1="450" y1="220" x2="200" y2="100"
                stroke="#555" stroke-width="1.5" marker-end="url(#arrow)"/>
          <text x="325" y="155" fill="#666" font-size="10" text-anchor="middle">
            controls
          </text>
    -->
  </svg>

  <!-- KEY LEADS -->
  <h2>Key Leads to Pursue</h2>
  <!-- One .lead-item per lead, ordered by priority -->
  <div class="lead-item">
    <div class="lead-priority">High Priority</div>
    <div class="lead-title">[Lead title]</div>
    <div class="lead-body">[What to do, where to look, why it matters.]</div>
  </div>

  <!-- ALLEGATIONS (UNVERIFIED) -->
  <h2>Allegations &amp; Unverified Claims</h2>
  <div class="allegation-box">
    <div class="label">Unverified — source: [source name]</div>
    [Allegation text]<sup>[N]</sup>
  </div>

  <!-- COVERAGE GAPS -->
  <h2>Coverage Gaps</h2>
  <table class="gap-table">
    <tr><th>Source</th><th>Status</th><th>Notes</th></tr>
    <tr>
      <td>GDELT (past 3 months)</td>
      <td class="gap-miss">Rate-limited</td>
      <td>Web search substituted</td>
    </tr>
    <!-- ... -->
  </table>

  <!-- FOOTNOTES -->
  <div class="footnotes">
    <strong>Sources</strong><br><br>
    [1] <a href="...">[Source title]</a> — [date]<br>
    <!-- ... numbered to match <sup> tags throughout -->
  </div>

</div>
</body>
</html>
```

---

**Graph generation guidance:**
- Assign each distinct entity type a fixed color (see comments in template).
- Position the primary company at center (roughly x=450, y=220 in a 900×440 viewBox).
- Cluster related entities spatially: subsidiaries below/near the parent,
  regulators upper-right, plaintiffs lower-left, individuals upper-left.
- Keep labels short (≤20 chars); wrap long names across two `<tspan>` lines.
- If the entity count exceeds ~12 nodes, omit minor entities and add a note
  below the graph: "N additional entities not shown — see Known Facts table."

**Writing rules for the HTML output:**
- Every factual claim in the report body must have a `<sup>[N]</sup>` inline
  footnote matching a numbered entry in the Sources section.
- Allegations and unverified claims must appear in `.allegation-box` elements,
  never in the Known Facts table.
- Timeline dot class must match event type: `founding` (green), `filing` (blue),
  `action` (red pulsing), `lawsuit` (orange).
- Coverage gaps table must include every source checked, not just the ones
  that failed.
- After writing the file, print the full file path so the user can open it.

## Handling ambiguity and non-findings

- No hits across all sources is a valid, useful result -- report it as
  "no adverse findings across the sources checked" rather than treating it
  as a failure.
- If a tool errors out (e.g. missing API key), tell the user which source
  couldn't be checked and why, so they know it's a coverage gap rather than
  a clean bill.
- Never fabricate a citation or a plausible-sounding case name/docket number
  if a search returns nothing -- report the gap instead.

## Setup notes (see mcp-servers/README.md for full instructions)

- GDELT tools work with no API key out of the box.
- OpenSanctions tools require `OPENSANCTIONS_API_KEY` to be set -- free for
  journalists, academic researchers, and anti-corruption work; commercial
  use requires a data license from OpenSanctions.
- Enigma has its own hosted MCP server (not bundled here) -- connect it
  separately per Enigma's documentation using your existing API key.
