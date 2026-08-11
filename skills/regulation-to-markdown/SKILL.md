---
name: regulation-to-markdown
description: Converts official regulation PDFs and other authoritative documents into source-grounded Markdown with the MinerU Precision API, deterministic normalization, page-by-page AI comparison, strict source restoration, overlap-safe merging, and release validation. Use when the user asks to convert, extract, audit, repair, merge, or validate an official PDF or legal document as Markdown.
---

# Regulation to Markdown

Produce a faithful Markdown representation of an official PDF. MinerU is an
extraction engine; the official PDF is the only authority.

Read [references/review-rules.md](references/review-rules.md) before auditing or
repairing source text.

## First-run setup

If the `regulation-to-markdown` MCP tools are unavailable:

1. Ask permission to run `python scripts/bootstrap.py` from this Skill.
2. Tell the user to reload Cursor after installation.
3. Stop the document workflow until the MCP server is available.

Do not install dependencies silently.

## Non-negotiable rules

1. Never infer missing legal wording from grammar, context, another law, or a
   similar provision.
2. Never silently correct an apparent source typo. If the official PDF contains
   it, preserve it and record it as a source anomaly.
3. Python may change formatting deterministically. Legal wording may change only
   through a source-verified finding with an official PDF page.
4. Do not submit to MinerU until the user explicitly confirms a split plan.
5. Keep raw PDF, split files, MinerU ZIPs, JSON, findings, and repair evidence.
   Only `FINAL.md` goes into the regulation knowledge-base slot.
6. A failed release gate blocks completion. Report the blocker; do not call an
   incomplete file final.

## Workflow

### 1. Inspect and propose

Call `inspect_pdf_and_propose_splits` with the official PDF and a dedicated work
directory.

Present both returned plans with:

- official page ranges;
- number of MinerU tasks;
- one-page overlaps;
- estimated sizes;
- whether OCR is likely required.

Use Cursor's question UI to ask the user to choose Reliable or Economical.
Do not choose for the user and do not call MinerU yet.

### 2. Confirm and extract

After the user chooses:

1. Call `confirm_split_plan` with the exact selected plan.
   If a physical chunk still exceeds 200 MB, return to inspection with a lower
   page target and ask the user to confirm the revised plan.
2. Call `submit_confirmed_batches_to_mineru`.
3. Use `mineru_batch_status` for progress. Long tasks may be resumed by batch ID.
4. Call `wait_for_and_download_mineru` when the user wants the job completed.

Defaults:

- model: `vlm`;
- language: choose the MinerU language pack from the source script; use `latin`
  for Latin-script documents, including Indonesian, and ask when uncertain;
- OCR: enable only for scanned or image-only PDFs;
- table recognition: enabled.

Never expose the MinerU token in chat, logs, findings, reports, or files.

### 3. Normalize each batch

For every downloaded MinerU directory:

1. Match the downloaded result's `data_id` to the confirmed batch. If MinerU
   omits `data_id`, use an exact unique file-name match; otherwise stop. Never
   rely on response order.
2. Call `locate_mineru_output` on its `result_dir`, passing the job `work_dir`.
3. Calculate the batch's official first page from the matched plan.
4. Call `normalize_mineru_batch`, passing the job `work_dir`.
5. Stop if visible-text integrity fails.
6. Treat unmatched page anchors, broken images, odd code fences, and table ranges
   as findings for source review.

Normalization is not legal repair.

### 4. Merge normalized batches

Call `merge_normalized_batches`, passing the job `work_dir`.

The tool must prove every overlap page is identical after deterministic
normalization. If an overlap differs, stop for manual source review. Never merge
by a generic marker such as `</table>`.

Only the successfully merged Markdown may enter AI audit.

### 5. Audit in bounded windows

Call `update_job_stage` with `ai_auditing`.
Call `initialize_ai_audit` for the merged Markdown, passing the job `work_dir`.
Use the returned windows exactly; do not skip or resize them after review
begins.

Audit the merged Markdown against the official PDF in source order.

- Use 10–20 PDF pages per review window.
- Detect the document's own hierarchy dynamically. Do not assume Indonesian
  BAB/Pasal structure.
- Review normative text, explanatory material, annexes, tables, signatures,
  diagrams, and page boundaries according to what the source actually contains.
- Use PDF text extraction for search. Call `render_official_pdf_pages`, passing
  the job `work_dir`, for layout-sensitive evidence such as tables, diagrams,
  signatures, columns, and disputed OCR.
- The audit pass must not edit Markdown.

Write one JSON object per line to `findings.jsonl`. Each finding must match the
schema in the review rules and include an exact PDF page.

After each window, call `record_ai_review_window`, passing the job `work_dir`,
with stage `audit` and status `completed` or `needs_review`.

### 6. Human approval and repair

Call `update_job_stage` with `ai_repairing`.

Show high/critical findings and all wording changes to the user.

Only an approved finding may set:

- `status: approved`;
- `source_verified: true`;
- `proposed_replacement`;
- confidence of at least 0.95.

Call `apply_source_verified_repairs` only after approval, passing the job
`work_dir`. The tool requires an exact, unique Markdown anchor and writes a
repair audit log.

For diagrams when the final deliverable must be one Markdown file:

- transcribe only visually verified labels, values, arrows, and relationships;
- label the block in English as not additional normative text;
- preserve any discrepancy between the diagram and surrounding source prose.

### 7. Independent verify

Call `update_job_stage` with `ai_verifying`.

Run a fresh verification pass that does not rely on the repair pass's
conclusions.

For each finding:

- mark `verified` only when the final Markdown matches the official PDF;
- mark `needs_review` when the PDF text layer and visual page differ;
- keep official-source anomalies verbatim.

After each window, call `record_ai_review_window`, passing the job `work_dir`,
with stage `verify`, the final Markdown path, and status `completed` or
`needs_review`. All verification windows must use the same final Markdown hash.

### 8. Validate and release

Call `validate_and_write_report` with the audit manifest and job `work_dir`.

Release only when:

- every official page is covered exactly once;
- page markers are unique;
- no local image reference is broken;
- every table-shape warning has been source-reviewed and resolved; a warning
  returns `needs_review` and blocks release even though it is not a hard failure;
- no unresolved high/critical finding exists;
- all applied repairs are source verified.

Deliver:

- `<document>_FINAL.md`;
- `validation-report.md`.

The validation report is a Markdown document with YAML frontmatter. Humans read
the body; programs read the frontmatter.

After validation, call `update_job_stage` with:

- `completed` when every release gate passes;
- `needs_human_review` when source evidence is ambiguous;
- `failed` with a short error when a blocking gate fails.
