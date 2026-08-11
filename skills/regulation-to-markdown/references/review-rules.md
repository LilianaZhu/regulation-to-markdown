# Source fidelity review rules

## Authority

The official PDF is the sole authority. MinerU Markdown, PDF text extraction,
language models, prior versions, and similar documents are secondary evidence.

## Change classes

### A — deterministic formatting

Examples: Markdown heading markers, blank lines, HTML tag layout, page comments,
and verified list breaks. The visible character stream must not change.

### B — official-source restoration

Examples: missing paragraph numbers, truncated text, OCR joins, wrong OCR
characters, and missing table rows. Requires exact PDF page evidence.

### C — official-source anomaly

The PDF itself contains a typo, duplicate word, inconsistent label, or
diagram/prose discrepancy. Preserve it verbatim and document it.

### D — editorial representation

Non-source text needed for a self-contained delivery, such as a verified diagram
transcription. Clearly label it as not additional normative text.

## Finding JSONL schema

One JSON object per line:

```json
{
  "finding_id": "finding-unique-id",
  "stage": "audit",
  "category": "missing_text",
  "severity": "high",
  "status": "open",
  "pdf_page": 138,
  "md_line_start": 5503,
  "md_line_end": 5506,
  "official_quote": "Exact source excerpt",
  "markdown_quote": "Exact current Markdown excerpt",
  "proposed_replacement": null,
  "rationale": "What differs and why it matters",
  "confidence": 0.99,
  "source_verified": false,
  "reviewer_notes": null
}
```

Allowed severities: `low`, `medium`, `high`, `critical`.

Allowed statuses: `open`, `approved`, `rejected`, `applied`, `verified`,
`needs_review`.

## Audit checklist

For each PDF page:

1. Confirm the first and last visible source text.
2. Compare every numbered or named structural node.
3. Check paragraph continuation across the previous and next page.
4. Check columns, footnotes, signatures, stamps, diagrams, and tables visually.
5. Confirm page headers/footers were not inserted into the legal text.
6. Record a finding for every uncertain difference; do not repair during audit.

Across each review window:

1. Confirm no source block is missing, duplicated, or reordered.
2. Confirm hierarchy reflects the source document's own hierarchy.
3. Check tables for missing main rows, columns, continuation rows, and flattened
   sub-items.
4. Check image references. If assets are absent, create a finding rather than a
   guessed transcription.

## Repair rules

1. Use the exact official wording and punctuation visible in the PDF.
2. Preserve source capitalization, numbering, terminology, and apparent typos.
3. Restrict the replacement to the smallest exact Markdown anchor.
4. Never combine unrelated clean-up with a source repair.
5. Set `source_verified: true` only after checking the PDF page.
6. Set `status: approved` only after user approval.
7. If an exact anchor is not unique, refine the finding; never replace all.

## Verification rules

Verification must use a fresh pass and compare the final file to the PDF again.

Mark a finding `verified` only when:

- the final wording matches the official source;
- the structure is attached to the correct parent;
- page-boundary placement is correct;
- no adjacent content was changed.

If the PDF text layer conflicts with the visual page, mark `needs_review` and
show both forms to the user.

## Severity guidance

- Critical: wrong legal obligation, missing article/section, or fabricated text.
- High: missing substantive paragraph, table row, definition, deadline, or
  source-unverified wording change.
- Medium: missing structural label, page-boundary error, flattened list, or
  broken image that affects retrieval.
- Low: harmless whitespace, source-code formatting, or a cosmetic inconsistency.
