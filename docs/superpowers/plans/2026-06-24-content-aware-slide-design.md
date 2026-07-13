# Content-Aware Slide Design Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a content-aware, project-specific page design pass after visual-direction selection and make both output renderers enforce it.

**Architecture:** Extend the shared SlideDeck contract with a deck design fingerprint and per-slide design plans. Build plans deterministically during assembly, then dispatch both PPTX and HyperFrames rendering from the same plan and reject low-diversity outputs in quality checks.

**Tech Stack:** Python 3.12, Pydantic, FastAPI, JSON Schema, TypeScript contracts, OOXML PPTX packaging, HTML/CSS/JavaScript, pytest.

---

### Task 1: Contract and invariants

**Files:**
- Modify: `packages/contracts/python/ai_ppt_contracts/slide_deck.py`
- Modify: `packages/contracts/typescript/index.ts`
- Generate: `packages/contracts/schemas/slide-deck-1.0.0.json`
- Test: `tests/test_contract_examples.py`

- [ ] Add failing tests requiring `designSystemId`, `designSeed`, and `designPlan` on every slide.
- [ ] Run the focused contract tests and confirm failure because those fields are absent.
- [ ] Add the Pydantic/TypeScript types and enforce page-image and composition-diversity invariants.
- [ ] Export the JSON schema and rerun contract tests.

### Task 2: Content-aware page planner

**Files:**
- Modify: `apps/api/app/services/slide_deck.py`
- Test: `apps/api/tests/test_slide_deck_api.py`

- [ ] Add failing tests for per-slide plans, no adjacent repeated archetype, content-sensitive evidence/process choices, and project-specific design IDs.
- [ ] Run the focused API tests and confirm expected missing-field/behavior failures.
- [ ] Implement stable project hashing, content signal classification, purpose pools, collision avoidance, image treatments, hierarchy, layers, and asset queries.
- [ ] Rerun the focused tests until green.

### Task 3: Shared renderer dispatch

**Files:**
- Modify: `apps/api/app/services/render.py`
- Test: `apps/api/tests/test_render_api.py`

- [ ] Add failing assertions for page-plan markers, multiple composition classes, per-page image treatments, and PPTX archetype markers.
- [ ] Run the render test and confirm those markers are absent.
- [ ] Make asset search/generation use `assetQuery` and `assetRole`.
- [ ] Add PPTX composition dispatch and image placement from `SlideDesignPlan`.
- [ ] Add HyperFrames composition classes/data attributes and archetype-specific CSS geometry/motion.
- [ ] Rerun the render tests until green.

### Task 4: Quality gate

**Files:**
- Modify: `apps/api/app/services/quality.py`
- Test: `apps/api/tests/test_quality_api.py`

- [ ] Add failing expectations for PPTX page-plan markers and HTML composition diversity.
- [ ] Run the focused quality test and confirm failure.
- [ ] Inspect artifacts for the markers and require sufficient archetype/treatment variety.
- [ ] Rerun quality tests until green.

### Task 5: Verification and project handoff

**Files:**
- Modify: `docs/PROJECT_STATE.md`

- [ ] Run contract tests, all backend tests, frontend typecheck, and frontend production build.
- [ ] Run a complete local generation smoke test with image search disabled so fallback behavior is deterministic.
- [ ] Inspect exported PPTX XML and HyperFrames HTML for one image per page and multiple design archetypes.
- [ ] Record verified behavior and artifact locations in project state.
