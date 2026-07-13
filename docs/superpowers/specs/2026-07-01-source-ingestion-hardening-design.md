# Source ingestion hardening design

Date: 2026-07-01

## Goal

Make source ingestion safer for large real-world PDF, DOCX, and PPTX files, and make partial understanding visible in `/workflow` before users approve an outline.

## Decisions

- Continue generation automatically when at least some useful text was extracted.
- Mark the source as `partial` when extraction hit the analysis character limit, skipped malformed document parts, failed individual pages/slides, or found pages with no machine-readable text.
- Keep OCR out of this slice. Image-only PDF pages are reported as unread instead of silently treated as understood.
- Preserve existing response fields (`sourcePack`, `extractedChars`, `truncated`) while adding diagnostics that the UI can render immediately.

## Backend contract

`POST /projects/{project_id}/sources/extract` continues to return a `SourcePack`, and adds:

- `understandingStatus`: `complete` or `partial`.
- `coverage`: unit, discovered count when known, processed, failed, skipped, analyzed characters.
- `warnings[]`: stable code, user-facing message, and affected unit labels when available.

`truncated` remains true for character-budget truncation. `understandingStatus` can be `partial` for non-truncation cases too, such as malformed optional DOCX parts or one broken PPTX slide.

## Parser approach

- Bound extraction at collection time instead of extracting the full document first.
- Use page/part/slide-level isolation so one bad unit does not discard the rest of the file.
- For OOXML, read only expected XML parts, use natural slide ordering, cap ZIP part sizes, and report malformed XML as partial when other text survives.
- For PDF, prefer `pypdf` page extraction with per-page failures; fall back to the existing lightweight stream scanner only as a recovery path.
- If no readable text is available, return a structured 422 instead of a partial empty source.

## `/workflow` UI

The reading report should show partial understanding at three levels:

1. Panel summary: how many sources were only partially read.
2. Source card status pill: `完整读取` or `部分读取`.
3. Warning block and coverage metrics inside each partial card, above the thesis.

The outline flow remains automatic, but copy explicitly says the deck will be based on the readable portion and may need user review against the original file.

## Regression tests

- Large text/DOCX/PPTX/PDF extraction returns partial diagnostics and does not analyze past the budget.
- Malformed DOCX/PPTX parts keep valid extracted text and report failed units.
- PPTX slide ordering is natural (`slide2` before `slide10`).
- Corrupt or unreadable files produce structured 4xx errors, not 500s.
- Existing text, DOCX, PPTX, and simple PDF happy paths continue to work.
