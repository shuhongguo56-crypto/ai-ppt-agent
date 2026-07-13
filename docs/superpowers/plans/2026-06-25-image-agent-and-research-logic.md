# Image Agent and Research Logic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit Image Agent planning contract and improve public research synthesis logic for tighter PPT outlines and content-serving images.

**Architecture:** Extend the existing SlideDeck contract with `ImagePlanItem`, generate the plan during SlideDeck assembly, consume it in render, and verify it in quality gates. Strengthen `research.py` synthesis so topic-only decks start from a logical argument chain rather than raw search fragments.

**Tech Stack:** FastAPI, Pydantic contracts, SQLite checkpoints, local PPTX renderer, HyperFrames HTML renderer, pytest, Next.js.

---

### Task 1: Image plan contract

**Files:**
- Modify: `packages/contracts/python/ai_ppt_contracts/slide_deck.py`
- Modify: `packages/contracts/python/ai_ppt_contracts/__init__.py`
- Modify: `packages/contracts/typescript/index.ts`
- Regenerate: `packages/contracts/schemas/slide-deck-1.0.0.json`
- Test: `tests/test_contract_examples.py`

- [ ] Add `ImageAssetType`, `ImageProviderAdapter`, and `ImagePlanItem`.
- [ ] Add `image_plan: list[ImagePlanItem]` to `SlideDeck`.
- [ ] Enforce one image plan item per slide and matching slide indexes.
- [ ] Update TypeScript contract.
- [ ] Regenerate schemas and run schema drift check.

### Task 2: Image Agent service

**Files:**
- Create: `apps/api/app/services/image_agent.py`
- Modify: `apps/api/app/services/slide_deck.py`
- Test: `apps/api/tests/test_slide_deck_api.py`

- [ ] Write a failing test that assembled decks expose `slideDeck.imagePlan` with one item per slide.
- [ ] Write a failing test that prompts include slide title/key point and are not generic decoration.
- [ ] Implement `build_image_plan(deck inputs)` with image type selection for background, course review, business scene, classical element, thesis concept, product showcase, icon illustration, and data visual.
- [ ] Wire the generated plan into `SlideDeck`.

### Task 3: Render consumes image plan

**Files:**
- Modify: `apps/api/app/services/render.py`
- Modify: `apps/api/app/services/quality.py`
- Test: `apps/api/tests/test_render_api.py`
- Test: `apps/api/tests/test_quality_api.py`

- [ ] Write a failing test proving render uses `imagePlan.searchQuery/prompt` instead of ad-hoc slide query generation.
- [ ] Render HTML with `data-image-plan-type`, `data-image-plan-purpose`, and provider metadata.
- [ ] Add PPTX hidden/marker metadata for Image Agent usage.
- [ ] Add quality checks for image-plan coverage in PPTX and HTML.

### Task 4: Research synthesis logic chain

**Files:**
- Modify: `apps/api/app/services/research.py`
- Modify: `apps/api/app/services/outline.py`
- Test: `apps/api/tests/test_research_service.py`
- Test: `apps/api/tests/test_outline_api.py`

- [ ] Write a failing test that AI + higher education synthesis contains central question, why-now, mechanism, evidence map, risk, and action sections.
- [ ] Write a failing test that outline narrative and slides reflect that logic chain.
- [ ] Implement sectioned synthesis helpers and make `_source_profile` prefer those sections.

### Task 5: Verification and live restart

**Files:**
- Modify: `docs/PROJECT_STATE.md`

- [ ] Run focused pytest suites.
- [ ] Run full backend tests.
- [ ] Run schema drift check.
- [ ] Run frontend production build.
- [ ] Generate a new local smoke deck and inspect PowerPoint-rendered PNGs.
- [ ] Restart API on `127.0.0.1:8000` and verify `/workflow`.
