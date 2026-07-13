# Readable Slide Content Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove internal planning language and text overflow from source-grounded PPTX/HyperFrames slides while preserving outline provenance.

**Architecture:** Clean audience-facing copy at HumanizePPT output, budget explainer labels in canonical SlideDeck assembly, and render non-duplicative geometry with native PowerPoint autofit. Automated quality checks enforce each boundary before PNG/PowerPoint visual QA.

**Tech Stack:** FastAPI, Pydantic, pytest, OOXML PPTX, HyperFrames HTML/CSS, PowerPoint COM for read-only QA rendering.

---

### Task 1: Audience-facing source-grounded outline copy

**Files:**
- Modify: `apps/api/tests/test_outline_api.py`
- Modify: `apps/api/app/services/outline.py`

- [ ] Add a failing regression assertion that visible titles, key points, and talking points contain none of the internal planning labels.
- [ ] Run the focused test and confirm it fails on the current `第 N 页`/`原文线索` output.
- [ ] Remove presentation-planning prefixes from visible fallback fields while retaining provenance in speaker notes and citation IDs.
- [ ] Re-run the focused outline suite.

### Task 2: Concise canonical explainer labels

**Files:**
- Modify: `apps/api/tests/test_slide_deck_api.py`
- Modify: `apps/api/app/services/slide_deck.py`
- Modify: `packages/contracts/python/ai_ppt_contracts/slide_deck.py`

- [ ] Add failing tests requiring two to four concise labels and forbidding internal planning prefixes.
- [ ] Run the focused deck tests and confirm current full-sentence labels fail.
- [ ] Implement clause-level label cleanup and deterministic display budgets using only outline-derived text.
- [ ] Add contract validation for the label count and maximum length, export schemas, and re-run focused tests.

### Task 3: Non-duplicative PPTX/HyperFrames explanation rendering

**Files:**
- Modify: `apps/api/tests/test_render_api.py`
- Modify: `apps/api/app/services/render.py`

- [ ] Add failing tests that explainer marker coverage remains complete, duplicate explainer cards disappear, HTML exposes at most three nodes per slide, and text shapes use native autofit.
- [ ] Run the focused render test and confirm failure.
- [ ] Replace repeated PPTX text cards with mode-specific editable geometry and add `a:normAutofit` to text/card body properties.
- [ ] Limit HTML explainer nodes to three concise labels and re-run render tests.

### Task 4: Quality gates and visual QA

**Files:**
- Modify: `apps/api/tests/test_quality_api.py`
- Modify: `apps/api/app/services/quality.py`
- Modify: `docs/PROJECT_STATE.md`

- [ ] Add failing quality assertions for PPTX autofit coverage and absence of internal planning labels.
- [ ] Implement quality checks and run the complete backend suite plus schema drift validation.
- [ ] Run the Next.js production build.
- [ ] Generate a new topic-only deck, export all slides to PNG, inspect slide 3 and the evidence slide, and query PowerPoint text bounds for remaining overflow.
- [ ] Record verification evidence and artifact paths in project state.
