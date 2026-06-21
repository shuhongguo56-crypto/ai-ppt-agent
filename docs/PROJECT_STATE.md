# AI PPT Agent Project State

Last updated: 2026-06-21

## What we are building

We are building an international bilingual AI PPT generation website / SaaS.

The product is not merely “make a PPT for the user.” It productizes the full AI PPT workflow:

1. User enters a topic, text, or uploads source material.
2. `HumanizePPT` analyzes the source and produces a structured outline decision.
3. The user can review, edit, or confirm the outline.
4. `Frontend-Slides` generates three high-end visual directions.
5. The user selects a direction.
6. The system assembles one canonical `SlideDeck JSON`.
7. The same `SlideDeck JSON` renders to editable PPTX and HyperFrames-style dynamic HTML.

## Product decisions

- First version: international version only, not a mainland-China-first version.
- Product surface: responsive web SaaS first; Windows/macOS clients can come later.
- Languages: Chinese/English bilingual UI and generation.
- Primary users: students, graduate students, teachers, international students, course reports, thesis defense, and business presentation users.
- Business model: subscription + credits. Early stage can use manual Alipay activation; automatic renewal can come later.
- Free tier: one-time 60 credits, outline plus 3-page watermarked preview only.
- Student: `$7.99/mo`, 250 credits, about 2 standard decks.
- Plus: `$14.99/mo`, 500 credits, about 5 standard decks.
- Pro: `$29.99/mo`, 1000 credits, about 10 standard decks.
- Annual plan: 20% monthly discount with annual credits.

## Technical architecture

- Frontend: Next.js.
- Backend: FastAPI.
- Local-first persistence: SQLite.
- Production persistence later: PostgreSQL.
- Queue later: Redis or equivalent.
- Object storage later: S3 / R2 / MinIO.
- Shared contract: versioned Slide/Outline/Visual JSON models.
- PPTX renderer: local renderer.
- HTML renderer: HyperFrames-style local renderer.
- Repository shape:
  - `apps/web`
  - `apps/api`
  - `packages/contracts`
  - `packages/render`
  - `packages/ui`
  - `packages/skills`
  - `tests`

## AI and model rules

- Content and outline model target: GPT-5.4 mini.
- Low-cost QA target: GPT-5.4 nano.
- AI original image target: GPT Image 2.
- Backup image model: Nano Banana 2 only if the user explicitly agrees.
- No automatic image-model fallback.
- Real images should prioritize authentic, licensed/free sources and store source/citation metadata.
- AI outputs should be structured JSON where possible.
- Ordinary frontend/log output must not expose full prompts, uploaded source text, base64 images, raw provider errors, or tracebacks.

## Skills inside the product

### HumanizePPT

Responsible for content analysis, audience/purpose detection, slide count and rhythm, outline decisions, per-slide planning, asset needs, citation needs, risks, and quality scores.

It outputs strict `OutlineDecision JSON`. It does not directly create PPT pages.

### Frontend-Slides

Responsible for producing three visual directions from an outline:

- Apple-style
- McKinsey-style
- Airbnb-style

The desired visual quality is premium, clean, less plastic, with strong whitespace, information hierarchy, cards, glassmorphism, masks, transparent overlays, and floating-card composition where useful.

## Generation workflow

Canonical flow:

`input/upload -> OutlineDecision -> outline review/confirmation -> 3 visual directions -> direction selection -> polish/texture layer -> SlideDeck JSON -> PPTX renderer -> HyperFrames renderer -> quality check -> export`

Important invariant:

`PPTX` and `HTML` must come from the same `SlideDeck JSON`.

## Local implementation status

The repository started essentially empty except for git metadata. The local-first foundation has been built in stages.

Known completed commits:

- `c9cb310 docs: define local foundation architecture`
- `0781870 docs: plan local foundation implementation`
- `e2f291d chore: ignore local worktrees`
- `5d8ee2f build: scaffold local monorepo`
- `d750f94 build: secure and pin scaffold dependencies`
- `9460422 build: align node engine with pnpm`
- `3bae45f build: pin python build backend`
- `e741e12 feat: add versioned cross-service contracts`
- `da5a93f fix: align contract constraints and parity`
- `8fb658f fix: harden contract validation and drift checks`
- `fe1b83c feat: add FastAPI service shell`
- `cb88597 build: align Starlette test client dependency`
- `b72bd5e feat: add local foundation services and model safety`
- `5f4bdf7 test: verify offline local foundation`
- `da0b0b7 fix: complete fake model gateway wiring`
- `3c54546 docs: add reconnection project state`
- `496be6a feat: add outline generation workflow`
- `f7b1fe2 feat: add visual direction workflow`

Implemented foundation areas:

- Monorepo scaffold.
- Versioned cross-service contracts.
- FastAPI shell and health route.
- Local SQLite project/checkpoint persistence.
- Skill registry for `HumanizePPT` and `Frontend-Slides`.
- Typed model gateway abstraction.
- Deterministic fake text/image gateways.
- Strict PNG validator.
- Local/offline test foundation.
- `OutlineDecision` contract, schema, TypeScript interface, generation/edit/confirm API.
- `VisualDirectionDecision` contract, schema, TypeScript interface, generation/select API.

## Current verified status

As of 2026-06-21, the local-foundation branch has passed:

- `python -m pytest -q -W error` — 226 passed.
- `pnpm test` — Python tests plus web/contracts TypeScript typecheck passed when bundled Python/Node/pnpm are placed on PATH.

## Next development target

Continue toward the actual product workflow:

1. Assemble deterministic `SlideDeck JSON` from a confirmed outline and selected visual direction.
2. Render PPTX and HyperFrames HTML from the same deck contract.
3. Build the bilingual Next.js workflow UI.
4. Add production model provider adapters behind the existing safe gateway interface.

## Reconnection summary for future sessions

If context is lost, remember this sentence:

“We are building an international bilingual AI PPT SaaS that converts user input into a reviewed outline, three premium visual directions, one canonical SlideDeck JSON, and then both editable PPTX and HyperFrames HTML.”
