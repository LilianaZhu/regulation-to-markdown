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
  "reviewer_notes": null,
  "visual_classification": null,
  "visual_disposition": null,
  "visual_description": null,
  "human_review_required": false,
  "human_reviewed": false
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

## Visual-content policy

Every reviewed image must be classified by its relationship to the regulation.

### Meaningful images

Examples include diagrams, flow charts, material illustrations, and images that
explain, qualify, or are needed to understand provisions.

- Set `category: meaningful_visual`.
- Set `visual_classification: meaningful` and
  `visual_disposition: described`.
- Transcribe only visually verified labels, values, arrows, and relationships.
- Put the description into `visual_description` and the final Markdown, clearly
  labelled in English as not additional normative text.
- Set `human_review_required: true` and `human_reviewed: false`.
- The validation report must show a warning and the document status must be
  `needs_review` until a human confirms the description.
- A generic statement that an image exists is not an adequate description.

### Non-substantive, low-information images

Examples include logos, coats of arms, electronic-signature verification QR
codes or URLs, handwritten signatures, seals, and similar images with little
information directly relevant to the provisions.

- They may be omitted from final Markdown.
- Set `category: non_substantive_visual`,
  `visual_classification: non_substantive`, and
  `visual_disposition: omitted`.
- Use `visual_description` to state exactly what was omitted and its PDF page.
- Mark the record verified after visual confirmation.
- The validation report must disclose the omission as information only. It must
  not create a warning or require human review.

An unclassified image finding is a release-blocking error.

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
  a meaningful image that is missing or inadequately described.
- Low: harmless whitespace, source-code formatting, or a cosmetic inconsistency.
- Omitted non-substantive images are informational records, not defects.
