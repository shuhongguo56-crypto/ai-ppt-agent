# Topic Research and Explainer Visuals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Research public sources automatically for topic-only requests and render an outline-grounded explanatory visual layer on every slide.

**Architecture:** A dedicated research service normalizes Wikipedia, OpenAlex, and Crossref results into the existing SourcePack contract before HumanizePPT runs. The canonical SlideDeck design plan gains explainer intent that is rendered by both PPTX and HyperFrames and enforced by quality checks.

**Tech Stack:** FastAPI, Pydantic, httpx, pytest, React/Next.js, OOXML PPTX, HTML/CSS/JavaScript.

---

### Task 1: Automatic topic research

**Files:**
- Create: `apps/api/app/services/research.py`
- Modify: `apps/api/app/config.py`
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/app/routes/outline.py`
- Modify: `conftest.py`
- Test: `apps/api/tests/test_outline_api.py`

- [ ] Add failing route tests proving topic-only generation returns a URL-backed `sourcePack`, research metadata, and citation IDs while supplied SourcePacks skip research.
- [ ] Run the focused outline tests and confirm the new assertions fail.
- [ ] Implement bounded public-source providers, normalization, deterministic fallback, and app-state injection.
- [ ] Pass the effective SourcePack into HumanizePPT and expose it in the response.
- [ ] Re-run the focused outline tests and confirm they pass without live network access in the default fixture.

### Task 2: Canonical explainer contract

**Files:**
- Modify: `packages/contracts/python/ai_ppt_contracts/slide_deck.py`
- Modify: `packages/contracts/typescript/index.ts`
- Modify: `packages/contracts/schemas/slide-deck-1.0.0.json`
- Modify: `apps/api/app/services/slide_deck.py`
- Test: `apps/api/tests/test_slide_deck_api.py`

- [ ] Add failing tests requiring `explanationMode`, `visualBrief`, and outline-derived `diagramLabels` on every page with mode diversity.
- [ ] Run the focused deck tests and confirm schema/field failures.
- [ ] Extend the contract and assembly planner with purpose- and content-aware explanation modes.
- [ ] Export schemas/types and re-run the focused deck tests.

### Task 3: Shared PPTX and HyperFrames explainer rendering

**Files:**
- Modify: `apps/api/app/services/render.py`
- Test: `apps/api/tests/test_render_api.py`

- [ ] Add failing render tests for PPTX `Page Explainer` markers, HTML `.explainer-layer`, labels, and `data-explanation-mode` coverage.
- [ ] Run the focused render tests and confirm they fail.
- [ ] Render editable PPTX nodes/arrows/callouts and the equivalent animated HTML explainer layer from the canonical design plan.
- [ ] Strengthen the asset query to use the visual brief and concrete diagram labels.
- [ ] Re-run render tests and inspect one generated PPTX/HTML pair.

### Task 4: Quality gates and Chinese workflow disclosure

**Files:**
- Modify: `apps/api/app/services/quality.py`
- Modify: `apps/web/app/workflow/WorkflowClient.tsx`
- Test: `apps/api/tests/test_quality_api.py`

- [ ] Add failing quality tests for per-page explainer coverage and explanation-mode diversity.
- [ ] Implement PPTX/HTML explainer checks.
- [ ] Update the workflow response type, no-material progress copy, and source report panel to show automatic web research sources and links.
- [ ] Run backend tests, frontend typecheck, and frontend production build.

### Task 5: End-to-end verification and documentation

**Files:**
- Modify: `docs/PROJECT_STATE.md`

- [ ] Run contract schema drift validation and the complete backend suite.
- [ ] Run a live topic-only HTTP workflow through outline, confirmation, visual selection, assembly, render, quality, and export.
- [ ] Verify every slide in both artifacts has an image and explainer layer, and verify retrieved source URLs appear in the outline response.
- [ ] Record the final behavior, commands, artifact paths, and remaining provider limitations in project state.
