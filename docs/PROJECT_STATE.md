# AI PPT Agent Project State

Last updated: 2026-07-14

## What we are building

We are building an international bilingual AI PPT generation website / SaaS.

The product is not merely 閳ユ笗ake a PPT for the user.閳?It productizes the full AI PPT workflow:

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
- `e6f3476 feat: assemble canonical slide deck`
- `d1c57ca feat: render slide deck artifacts`
- `f9348fd feat: build bilingual workflow landing page`
- current work: export/download endpoints, quality gate, source notes, credits quote, interactive workflow UI

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
- `SlideDeck` contract, schema, TypeScript interface, and canonical assembly API.
- `RenderResult` contract, schema, TypeScript interface, and local PPTX + HyperFrames HTML rendering API.
- Bilingual Next.js landing page.
- Interactive Next.js `/workflow` page that runs the local API chain to downloads, including source notes and credits quote.
- Export/download endpoints for PPTX and HyperFrames HTML.
- Quality gate that validates render artifacts before export.
- Local credits quote API and plan catalog.
- Local start scripts for API and Web.
- File extraction routes for TXT/Markdown/DOCX/PPTX/PDF source material.
- OpenAI and Ollama model gateway adapters behind the safe structured-generation interface.
- Multi-provider `cascade` text gateway that can try OpenAI, Gemini-compatible, OpenRouter, Groq, local OpenAI-compatible servers, Ollama, and enhanced local fallback.
- Real-model prompts for `HumanizePPT` and `Frontend-Slides` now explicitly require premium personalized storylines, audience fit, evidence planning, and non-template visual art direction.
- Chinese-first conversational workflow UI with outline review, three visual-direction choices, and visual mini-previews.
- Content-aware local fallback outlines that use source summaries in evidence/insight slides.
- PPTX renderer with layout-specific slide compositions, card/shadow styling, and real PowerPoint speaker-note slide parts.
- HyperFrames HTML renderer with layout-specific dynamic presentation frames.
- Impeccable product context for the web app (`apps/web/PRODUCT.md`) plus local live-mode config for future design iteration.
- Web UI polish pass: homepage copy now frames the product as content-aware visual-direction generation rather than template swapping; `/workflow` now has a clearer user-facing generation stage rail, compact cascade provider-chain pills, scoped visual-direction previews, stronger focus states, reduced-motion handling, and more professional visual-direction evidence cards.
- Customer-facing gallery pass: `/workflow` now defaults to a short outcome-led hero, an original MotionSites-inspired dynamic PPT gallery, and a true seven-screen briefing wizard. Only the current question renders; `下一步` replaces the page with a horizontal transition, previous answers do not accumulate, and the result view stays hidden until generation starts. API/model/image/provider explanations and design diagnostics remain available only through a compact fixed `专业设置` control. Desktop and 390px mobile audits confirmed one visible wizard page, stable scroll position across steps, no horizontal overflow, and no backend terms in the collapsed customer view. Reusable art-direction prompts live in `docs/FRONTEND_VISUAL_PROMPTS.md`.
- Project library page (`/projects`) with real local project history, search/filter controls, generation progress rails, readable fallbacks for corrupted legacy smoke-test text, and direct preview/download links for completed PPTX + HyperFrames HTML exports.
- Strict outline-first generation gate: outline generation always creates a draft review checkpoint, including one-click mode; visual directions, SlideDeck assembly, render, and export remain blocked until the outline is explicitly confirmed.
- SlideDeck/render content provenance hardening: generated slide titles, subtitles, block text, visual intent, and speaker notes now derive from `OutlineDecision` fields only; renderer no longer injects visible fixed labels such as section markers, card role labels, theme names, or generic closing copy into PPTX/HyperFrames slide content.
- Workflow UI now explicitly shows the file-to-outline step: uploaded files are parsed into `SourcePack`, HumanizePPT creates the PPT outline, and the user confirms the outline before visual generation.
- Source parsing depth upgrade: TXT/Markdown/DOCX/PPTX/PDF extraction now builds a structured reading report inside `SourcePack.summary` with title/theme, thesis, structure, key arguments, evidence/data, PPT outline suggestions, and representative excerpts. Pasted text in `/workflow` now goes through the same source extraction route instead of being shallowly truncated.
- HumanizePPT local fallback now parses that structured `SourcePack` report into a source-grounded `OutlineDecision`; slide titles, key points, talking points, speaker notes, citation IDs, and asset needs are adapted from the uploaded article's actual thesis/arguments/evidence.
- Frontend-Slides local fallback now leaves verifiable traces in `VisualDirectionDecision`: generatedBy skill remains `Frontend-Slides`, visual directions adapt to evidence-heavy outlines, sample slide intents quote each outline slide's concrete keyPoint/evidence, and risk/layout notes state that the planner used the confirmed outline rather than fixed template text.
- HyperFrames HTML now declares renderer metadata (`HyperFrames local renderer`, `SlideDeck JSON`, `data-hyperframes-renderer="local"`), and quality/export path validation now handles both absolute artifact paths and `.local/assets/...` relative paths safely.
- `/workflow` now shows a first-class `资料理解报告` panel before outline confirmation. It summarizes each parsed source's core theme, thesis, key arguments, evidence/data, PPT structure suggestions, excerpts, extracted character count, and truncation status so the user can verify file understanding before continuing.

- Visual-direction planning is now an explicit `Frontend-Slides + HyperFrames` collaboration. Each `VisualDirection` includes `motionPlan`, `layeringPlan`, `imageStrategy`, and `hyperframesPlan`; fallback generation fills these with concrete animation, hierarchy, image-search, and dynamic-HTML plans.
- SlideDeck assembly now gives every slide an outline-derived `image_placeholder` block (`requiredAssets` or `visualIntent`), keeping image planning grounded in the confirmed outline.
- Rendering now resolves one real visual asset per slide: it derives the query from the user/source-grounded SlideDeck content, attempts open/licensed web image search via Wikimedia Commons metadata, falls back to GPT Image 2 through the configured image gateway, and finally falls back to a deterministic local SVG if needed.
- PPTX now embeds slide visuals under `ppt/media/*` with per-slide image relationships and `<p:pic>` elements. HyperFrames HTML now renders `<figure class="frame-asset">` per slide with source/query/attribution metadata, image/card animations, keyboard navigation, and `prefers-reduced-motion` fallback.
- Quality checks now verify PPTX media assets, HTML visual assets, HyperFrames renderer markers, motion markers, and reduced-motion support.
- Reference-PPT fidelity pass: uploaded `.pptx` sources now produce a visual fingerprint in `SourcePack.summary` (slide count, media counts, dominant colors, fonts, picture density, full-bleed image coverage, transition/timing hints, and style suggestions), so reference decks influence outline/visual planning instead of being treated as shallow text.
- Source upload limit was raised from 10MB to 60MB so realistic client decks such as the 36.6MB `最终版.pptx` reference can be parsed locally.
- PPTX renderer now uses a reference-grade cinematic baseline inspired by the supplied deck: every generated slide gets a full-bleed visual layer, dark reading vignette, cream text, gold accent spine/baseline, red/blue light-field overlays, and editable foreground text/cards from the canonical `SlideDeck JSON`.
- HyperFrames HTML now mirrors that reference style with `data-reference-style="cinematic-full-bleed"`, full-bleed background figures, dark overlay/vignette, light-sweep motion, staggered foreground cards, keyboard navigation, and reduced-motion fallback.
- Quality gate now verifies reference-style fidelity, including per-slide PPTX full-bleed visual layers and HTML cinematic full-bleed markers, not just file existence.
- HyperFrames export is now packaged for real handoff: inline preview still streams `hyperframes.html`, while the normal `hyperframes_html` download returns `hyperframes-package.zip` containing the HTML plus `assets/*` so users can unzip and open the presentation offline without losing images.
- `/workflow` and `/projects` now label this as an HTML 演示包 instead of a single HTML file, keeping the user-facing promise accurate.

## Current verified status

As of 2026-06-24, the local-foundation branch has passed:

- `.venv\Scripts\python.exe -m pytest -q` -> 275 passed, after deep source parsing, Frontend-Slides evidence intents, HyperFrames markers, image-asset rendering, and export path hardening.
- `pnpm --filter @ai-ppt/web typecheck` -> TypeScript contract/web typecheck passed with bundled Node/pnpm.
- `pnpm --filter @ai-ppt/web build` -> Next.js production build passed.
- Real reference-file smoke passed with `D:\Codex\Workspaces\ai-ppt-reference-final\reference-final.pptx` (36.6MB): source extraction -> outline -> visual directions -> selected direction -> SlideDeck -> PPTX + HyperFrames HTML -> quality gate all completed.
- A user-facing smoke artifact was copied to `D:\Codex\Outputs\ai-ppt-client-smoke-final-effect-1782280549`; it contains `deck.pptx`, `hyperframes.html`, and `assets/*`. The generated PPTX has 8 slides, 8 media assets, and 8/8 reference full-bleed visual layers.
- Export regression passed: `hyperframes_html?inline=true` returns preview HTML, while `hyperframes_html` downloads a ZIP package containing `hyperframes.html` and slide visual assets.
- Local HTTP smoke test passed for: source extraction reading report -> HumanizePPT source-grounded outline -> 3 Frontend-Slides visual directions with source evidence intents -> selected direction -> canonical SlideDeck JSON -> PPTX + HyperFrames HTML -> quality gate -> exports.
- Local HTTP gate smoke test passed: outline generation returned `draft/outline_review`, visual generation before outline confirmation returned 409, confirmation then allowed visual direction generation, SlideDeck assembly, quality check, and exports.
- Local browser/API check passed for `http://127.0.0.1:3001/workflow`; current dev servers are API `http://127.0.0.1:8000` and Web `http://127.0.0.1:3001`. The latest smoke project confirmed `/workflow` 200, HyperFrames inline preview 200 with renderer marker, and PPTX download 200.
- Local browser/API check passed for `http://127.0.0.1:3001/projects`; latest completed project export links returned PPTX and inline HTML successfully.

## Content-aware page design pass

- Visual-direction selection is followed by a real per-slide design-planning pass.
- Canonical `SlideDeck JSON` includes a project-specific `designSystemId`, deterministic `designSeed`, and one `SlideDesignPlan` per slide.
- Each plan records composition archetype, project-seeded variant, image treatment, asset role/query, density, hierarchy, layers, motion preset, and rationale.
- Adjacent slides cannot reuse the same composition archetype. Decks of six or more slides require at least three archetypes and two image treatments.
- Every slide must include a content-grounded image placeholder and asset query.
- PPTX and HyperFrames HTML consume the same page plan across cover, index, editorial, evidence, data, process, system-map, comparison, priority, and closing families.
- The selected visual-direction palette now drives PPTX, HTML, and deterministic local fallback visuals; projects are no longer forced into one dark reference skin.
- `/workflow` surfaces the completed page-by-page design plan after export.
- PPTX packaging now starts from a small PowerPoint-native compatibility template with valid master, layout, notes master, theme, view, table-style, and relationship parts. This fixes the prior package that passed ZIP/XML checks but PowerPoint rejected as corrupted.
- Quality checks now include page-plan markers, HTML composition diversity, and the PowerPoint-native scaffold.
- Latest verification: 276 backend tests passed; frontend typecheck and production build passed.
- Real Office smoke: 8 slides used 8 composition archetypes and 4 image treatments, passed every quality check, and opened successfully in PowerPoint 16.0.
- User-facing artifacts: `D:\Codex\Outputs\ai-ppt-content-aware-final-v3\content-aware-deck.pptx` and `D:\Codex\Outputs\ai-ppt-content-aware-final-v3\content-aware-hyperframes.html`.

## Next development target

Continue toward the actual product workflow:

1. Improve real-model prompt quality and provider configuration UX.
2. Deepen cross-source fact checking, citation formatting, and licensed-image attribution beyond the current public-source cascade.
3. Add auth, billing, credits ledger, and production persistence.
4. Add richer PPTX fidelity such as editable charts, image assets, and more advanced typography controls.
5. Add deeper project resume/edit actions after history selection.

## Reconnection summary for future sessions

If context is lost, remember this sentence:

We are building an international bilingual AI PPT SaaS that converts user input into a reviewed outline, three premium visual directions, one canonical SlideDeck JSON, and then both editable PPTX and HyperFrames HTML.

## Topic-only research and explainer-visual pass

Completed on 2026-06-24:

- Topic-only outline generation now performs a bounded public-source cascade before HumanizePPT: Wikipedia provides the topic overview, OpenAlex is attempted for scholarly evidence, and Crossref supplies publication metadata when OpenAlex is unavailable.
- Retrieved pages and publications are normalized into the existing `SourcePack` contract with stable source IDs, HTTPS URLs, thesis, key arguments, evidence notes, PPT-flow suggestions, and excerpts. User-supplied SourcePacks remain authoritative and skip automatic research.
- If public retrieval fails, the response explicitly reports `local_fallback`; it never presents the fallback as successful web research.
- `/outline/generate` now returns the effective `sourcePack` plus research mode/providers/warnings. `/workflow` shows those sources, summaries, and original-source links before outline review.
- Canonical `SlideDesignPlan` now includes `explanationMode`, `visualBrief`, and `diagramLabels`. Diagram labels are derived only from the outline slide title, key point, and talking points.
- PPTX and HyperFrames HTML render the same explainer plan. PPTX uses editable nodes/connectors and a `Page Explainer` marker; HTML uses animated `.explainer-layer` nodes with reduced-motion support.
- Quality gates require one explainer layer per slide and at least three explanation modes in decks of six or more slides.
- Verification: contract drift check passed; backend suite passed with 281 tests; Next.js typecheck and production build passed.
- Real topic-only smoke (`生成式人工智能在高等教育中的应用`) retrieved five public sources from Wikipedia/Crossref, generated eight slides, used five explanation modes, produced eight PPTX media assets, and passed every quality check.
- PowerPoint 16.0 opened the generated eight-slide deck successfully without repair.
- Verified artifacts: `D:\Codex\Outputs\ai-ppt-topic-research-explainer-20260624\renders\topic-research-explainer-20260624\slide-deck-v1\deck.pptx` and `D:\Codex\Outputs\ai-ppt-topic-research-explainer-20260624\renders\topic-research-explainer-20260624\slide-deck-v1\hyperframes.html`.
- Current local services were restarted on the latest code: Web `http://127.0.0.1:3001/workflow`; API `http://127.0.0.1:8000`. Live API smoke returned `researchMode=web`, providers `wikipedia,crossref`, five sources/citations, and eight outline slides.

## Readable source-grounded slide QA pass

Completed on 2026-06-25:

- Topic-only research now inserts a first-class synthesis source ahead of raw public web sources when the topic needs higher-level interpretation. For the AI + higher-education smoke, the synthesis frames generative AI as a shift from tool usage toward coordinated redesign of teaching, learning support, assessment, and governance.
- Source-grounded HumanizePPT visible copy is now more presentation-safe: internal planning labels are removed, CJK slide titles/key points/talking points are compacted, and generated copy avoids exposing raw source-pack labels to users.
- Diagram labels are capped and cleaned before they enter SlideDeck JSON, preventing long source excerpts or internal planning labels from appearing as visual nodes.
- PPTX text bodies now use native autofit, and quality gates verify PPTX/HTML visible-copy hygiene plus encoding integrity, including replacement-character or repeated-question-mark mojibake.
- Evidence-slide design planning now distinguishes real quantitative signals from citation years. A 2025 paper title plus qualitative words such as “降低/提升” no longer triggers a fake data-landscape/bar-chart layout; it uses `proof_mosaic` unless the slide contains actual chartable quantities such as percentages, sample counts, people counts, money, or ratios.
- PPTX rendering no longer duplicates explainer text into extra visible cards. Non-text explainer geometry remains editable while slide text stays outline-derived.
- Real v6 topic-only smoke completed on the local API with Chinese UTF-8 requests: public research -> HumanizePPT outline -> three Frontend-Slides visual directions -> `data_story` selection -> canonical SlideDeck JSON -> PPTX + HyperFrames HTML -> quality gate.
- v6 quality gate passed all 25 checks, including PPTX media assets, full-bleed visual layers, page-plan markers, explainer layers, text autofit, visible-copy hygiene, encoding integrity, HyperFrames markers, motion, reduced-motion support, and HTML composition diversity.
- PowerPoint 16.0 opened the v6 deck, exported 8/8 slides to PNG, and reported 0 visible text overflows. Visual QA confirmed the evidence slide uses a proof mosaic / relationship-node treatment instead of a fake bar chart.
- Verification: contract schema drift check passed; `.venv\Scripts\python.exe -m pytest -q` -> 287 passed; `pnpm --filter @ai-ppt/web build` passed.
- Verified artifacts: `D:\Codex\Outputs\ai-ppt-readable-final-20260625-v6\renders\readable-topic-only-20260625-v6\slide-deck-v1\deck.pptx` and `D:\Codex\Outputs\ai-ppt-readable-final-20260625-v6\renders\readable-topic-only-20260625-v6\slide-deck-v1\hyperframes.html`.

## Image Agent, thin-research hardening, and temporary Pages deployment

Completed on 2026-06-25:

- Added first-class `ImagePlanItem` to the canonical `SlideDeck JSON`. Every slide must now have an `imagePlan` item with `slide`, `needsImage`, `imageType`, `prompt`, `purpose`, `searchQuery`, and a replaceable provider chain.
- Reserved the image provider adapter chain in code: `open_web_search -> OpenAI Image API -> Midjourney API -> Stable Diffusion API -> custom image2 API -> local_svg_fallback`.
- Added backend `Image Agent` planning. It chooses content-serving image types such as background, course-review atmosphere, business scene, classical element, thesis concept, product showcase, icon/illustration, and data visual from the slide purpose, deck type, design plan, and outline content.
- PPTX and HyperFrames HTML now render Image Agent markers from the same canonical deck. PPTX includes hidden `Image Agent ...` markers; HTML figures include `data-image-plan-type`, `data-image-plan-purpose`, and `data-provider-chain`.
- Local/fake image generation is no longer a flat color tile. When no real image API is configured, it generates deterministic prompt-aware PNG visuals for classroom/review, business, classical, product, icon, data, thesis, and background roles.
- Topic research now appends a research-gap logic brief when live web retrieval is too thin. This prevents a shallow outline from pretending incomplete web evidence is enough; the outline receives explicit central-question, mechanism, evidence-map, risk-boundary, and audience-action guidance.
- GitHub Pages static frontend deployment was created at `https://shuhongguo56-crypto.github.io/ai-ppt-agent/` with workflow route `https://shuhongguo56-crypto.github.io/ai-ppt-agent/workflow/`.
- The static frontend supports runtime API override through `?api=https://your-api.example.com/api`; default is `http://127.0.0.1:8000/api`. FastAPI CORS now includes `https://shuhongguo56-crypto.github.io`.
- Verification: `.venv\Scripts\python.exe -m pytest -q` -> 289 passed; GitHub Pages root and `/workflow/` both returned HTTP 200; `pnpm --filter @ai-ppt/web build` passed with `GITHUB_PAGES_REPO=ai-ppt-agent`.
- Real v6 Image Agent smoke used Unicode-safe HTTP requests, retrieved web sources from Wikipedia/Crossref, generated 8 slides and 8 image-plan items, and passed the quality gate with no failed checks.
- PowerPoint 16.0 opened the v6 deck, exported 8/8 slides to PNG, found 15 picture shapes, 8 Image Agent markers, and 0 text overflows.
- Verified artifacts: `D:\Codex\Outputs\ai-ppt-image-agent-20260625-v4\renders\image-agent-smoke-20260625-v6\slide-deck-v1\deck.pptx` and `D:\Codex\Outputs\ai-ppt-image-agent-20260625-v4\renders\image-agent-smoke-20260625-v6\slide-deck-v1\hyperframes.html`.

## Public live smoke through GitHub Pages + Cloudflare tunnel

Completed on 2026-06-30:

- Local FastAPI was restarted from the active worktree on `http://127.0.0.1:8000` with outputs under `D:\Codex\Outputs\ai-ppt-live-20260630` and SQLite state under `D:\Codex\Workspaces\ai-ppt-live-20260630`.
- Local Next.js web was restarted on `http://127.0.0.1:3001/workflow/`.
- A Cloudflare quick tunnel exposes the local API at `https://permalink-comments-exact-explanation.trycloudflare.com`; PID is stored at `D:\Codex\Workspaces\ai-ppt-live-20260630\cloudflared.pid`.
- A GitHub Pages convenience redirect was added at `https://shuhongguo56-crypto.github.io/ai-ppt-agent/live/`; it redirects to `/workflow/?api=https%3A%2F%2Fpermalink-comments-exact-explanation.trycloudflare.com%2Fapi`.
- Public API health and runtime checks passed through the tunnel.
- Public API end-to-end smoke `public-tunnel-smoke-20260630-v1` completed: project creation -> web research -> outline draft/confirm -> visual directions -> `data_story` selection -> SlideDeck assembly -> render -> quality -> exports.
- Smoke result: research mode `web`, providers `wikipedia,crossref`, 8 slides, 8 image-plan items, quality passed with no failed checks.
- Public download checks succeeded through the tunnel for `deck.pptx`, `hyperframes-package.zip`, and inline preview HTML.
- PowerPoint 16.0 opened the downloaded public-smoke PPTX, exported 8/8 slides to PNG, found 13 picture shapes, 8 Image Agent markers, and 0 text overflows.
- User-facing public-smoke artifacts: `D:\Codex\Outputs\public-tunnel-smoke-20260630-v1\deck.pptx`, `D:\Codex\Outputs\public-tunnel-smoke-20260630-v1\hyperframes-package.zip`, and `D:\Codex\Outputs\public-tunnel-smoke-20260630-v1\hyperframes-preview.html`.
- Important limitation: this is not yet a permanent backend. The GitHub Pages URL is permanent; the Cloudflare quick tunnel remains available only while this Windows machine and the `cloudflared` process keep running. Production needs a hosted backend or named Cloudflare Tunnel/custom domain.

## API connection self-healing UI pass

Completed on 2026-06-30:

- `/workflow` now has a first-class backend connection panel in the hero area. It shows whether the FastAPI backend is connected, the currently active API base URL, the current model mode, and the provider chain.
- Users can paste a replacement API URL directly in the page and click `重新连接`. This makes the GitHub Pages/static frontend recoverable when a Cloudflare quick-tunnel URL changes, instead of silently failing.
- The API URL normalization accepts either an origin such as `https://example.com` or a full `/api` base such as `https://example.com/api`; blank input safely falls back to the local default.
- Runtime API base selection now supports an in-session override. A `?api=...` query parameter still seeds the page, but if the user edits the API field, subsequent workflow/export requests use the edited value instead of repeatedly being forced back to the query URL.
- The disabled primary action state was fixed so disabled buttons remain readable against the dark UI.
- Verification after this pass:
  - `.venv\Scripts\python.exe -m pytest -q` -> 289 passed.
  - `pnpm --filter @ai-ppt/web typecheck` -> passed with bundled Node on PATH.
  - `pnpm --filter @ai-ppt/web build` -> passed.
  - `GITHUB_PAGES_REPO=ai-ppt-agent pnpm --filter @ai-ppt/web build` -> passed, and the static export was pushed to the GitHub Pages repo in commit `b33104b Improve live API connection panel`.
  - Public GitHub Pages `/workflow/` refreshed successfully and now contains the new `API 地址` / `后端连接` connection panel.
  - Public `/live/` still points at the active Cloudflare quick tunnel for the local API.
  - `http://127.0.0.1:3001/workflow/?api=http%3A%2F%2F127.0.0.1%3A8000%2Fapi` -> HTTP 200, rendered `API 地址`, rendered `AI PPT 对话生成`, and did not contain Next.js error-overlay markers.
  - Headless Edge screenshot verified the new connection panel, normal Chinese text, and readable disabled button state. Screenshot: `D:\Codex\Outputs\ai-ppt-ui-api-connection-20260630\workflow-api-panel-v2.png`.
  - Public API smoke `public-ui-panel-smoke-unicode-1782823664` completed through the Cloudflare tunnel: web research -> outline confirm -> 3 visual directions -> direction selection -> SlideDeck -> render -> quality -> exports. Result: `web` research via `wikipedia,crossref`, 8 slides, 8 image-plan items, quality passed, exports returned PPTX and HyperFrames ZIP.

## Source ingestion hardening pass

Completed on 2026-07-01:

- Source extraction now returns first-class partial-understanding diagnostics for text, DOCX, PPTX, and PDF uploads while preserving the existing `sourcePack`, `extractedChars`, and `truncated` fields.
- `/projects/{project_id}/sources/extract` now includes `understandingStatus`, `coverage`, and stable warning objects with affected unit labels when available.
- Large sources are bounded during extraction instead of being fully read before truncation. DOCX/PPTX XML parts and PDF pages are isolated so one malformed part/page does not discard valid extracted text.
- PPTX extraction keeps natural slide ordering (`slide2` before `slide10`) and still captures the visual fingerprint used by later visual-direction generation.
- Image-only or unreadable PDF pages are reported as partial understanding; OCR remains intentionally out of scope for this slice.
- Corrupt/unreadable files return structured 4xx errors instead of leaking parser exceptions.
- `/workflow` now surfaces partial understanding in the reading report: panel summary, per-source status pill, warning block, coverage metrics, and copy that tells the user generation continues from the readable portion.
- Verification:
  - `.venv\Scripts\python.exe -m pytest -q` -> 302 passed.
  - Bundled Node `pnpm --filter @ai-ppt/web typecheck` -> passed.
  - Bundled Node `pnpm --filter @ai-ppt/web build` -> passed.

## Local customer-delivery final pass

Completed on 2026-07-03:

- Active local services are `http://127.0.0.1:8000/api` for FastAPI and `http://127.0.0.1:3001/workflow/` for the Chinese workflow UI.
- Final demo/customer project: `client-luckin-final-20260703035037`, topic `瑞幸咖啡品牌复兴与新消费增长策略`, audience `品牌咨询客户和投资人`.
- Ran the complete product pipeline from a UTF-8 source pack: project create -> source-grounded HumanizePPT outline -> outline confirm -> three Frontend-Slides visual directions -> `product_showcase` selection -> canonical SlideDeck JSON -> PPTX + HyperFrames HTML render -> quality check.
- Fixed a PPTX-only visible-copy compaction bug where quoted business concepts could be removed and leave malformed phrases such as `一个的经营样本`. Added regression coverage for keeping required quoted business concepts.
- Final delivery QA passed: 8 slides, 8 image-plan items, 8 embedded PPTX media assets, 8 HTML image assets, 29 quality checks passed, no `???`, no `原文没有明显数字型证据`, no `一个的经营样本`, and PPTX contains the key logic terms `信任修复`, `产品矩阵`, and `门店密度`.
- Verification after this pass:
  - `.venv\Scripts\python.exe -m pytest --basetemp D:\Codex\Workspaces\...\basetemp -q` -> 321 passed.
  - Bundled Node `pnpm --filter @ai-ppt/web typecheck` -> passed.
  - Bundled Node `pnpm --filter @ai-ppt/web build` -> passed.
  - `curl.exe -I -L http://127.0.0.1:3001/workflow/` -> HTTP 200.
- User-facing final artifacts: `D:\Codex\Outputs\ai-ppt-client-final-20260703035037\deck.pptx`, `D:\Codex\Outputs\ai-ppt-client-final-20260703035037\hyperframes-inline.html`, and `D:\Codex\Outputs\ai-ppt-client-final-20260703035037\hyperframes-package.zip`.

## PowerPoint show-safe rendering pass

Completed on 2026-07-03:

- User feedback showed that the previous PPTX opened but still looked too visually noisy in slideshow: full-bleed AI images contained fake UI/text artifacts, dark overlays reduced readability, and large/card text competed with imagery.
- Real PowerPoint COM verification confirmed the prior deck was structurally openable, but visual QA from exported PNGs exposed the layout problem.
- PPTX rendering was changed to a show-safe customer-delivery mode:
  - fixed light background and dark Chinese text for PPTX output;
  - controlled right-side visual window instead of visible full-slide image backgrounds;
  - high-opacity white content cards;
  - tighter visible-copy clipping for title/body/card text;
  - unified left-side safe text area for all PPTX slides;
  - Pollinations/free image fallback is no longer accepted into PPTX by default because it can generate fake words/UI; set `AI_PPT_ALLOW_RISKY_FREE_AI_IMAGES=true` only when explicitly testing that provider.
- Final show-safe demo project: `client-luckin-show-safe-20260703124310`.
- PowerPoint 16.0 opened the show-safe deck, exported 8/8 slides to PNG, and SlideShowSettings accepted slides 1-8.
- Final show-safe QA passed: 8 slides, 8 image-plan items, 8 embedded PPTX media assets, 8 local PNG HTML assets, 29 quality checks passed, no `???`, no `原文没有明显数字型证据`, no `一个的经营样本`, and PPTX contains `信任修复`, `产品矩阵`, and `门店密度`.
- Verification:
  - `apps/api/tests/test_render_api.py apps/api/tests/test_quality_api.py` -> 17 passed.
  - `.venv\Scripts\python.exe -m pytest --basetemp D:\Codex\Workspaces\...\basetemp -q` -> 321 passed.
  - `curl.exe -I -L http://127.0.0.1:3001/workflow/` -> HTTP 200.
- User-facing show-safe artifacts: `D:\Codex\Outputs\ai-ppt-client-show-safe-20260703124310\deck.pptx`, `D:\Codex\Outputs\ai-ppt-client-show-safe-20260703124310\hyperframes-inline.html`, `D:\Codex\Outputs\ai-ppt-client-show-safe-20260703124310\hyperframes-package.zip`, and exported PowerPoint QA contact sheet `D:\Codex\Outputs\ai-ppt-client-show-safe-20260703124310\powerpoint-open-test\contact-sheet.png`.

## HyperFrames PPT-like preview controls

Completed on 2026-07-03:

- Added PPT-like preview controls to the HyperFrames HTML renderer and patched the current show-safe HTML artifact in place.
- The exported HTML now includes `全屏放映`, `适配窗口`, `−`, `＋`, `上一页`, `下一页`, and `讲稿` controls.
- `全屏放映` uses the browser Fullscreen API when available and falls back to a no-margin presenter layout when file/browser restrictions block fullscreen.
- Presenter mode fits the 16:9 frame to the viewport (`width: min(100vw, calc(100dvh * 16 / 9))`, `height: min(100dvh, calc(100vw * 9 / 16))`), removes rounded frame chrome, and dims controls until hover/focus.
- Keyboard shortcuts: `F` toggles presenter/fullscreen, `+`/`-` zoom, `0` fit, arrows/space navigate, `N` toggles speaker notes.
- Current patched artifact: `D:\Codex\Outputs\ai-ppt-client-show-safe-20260703124310\hyperframes-inline.html`. The matching zip was refreshed with the patched HTML and all 8 image assets.
- Verification: `apps/api/tests/test_render_api.py` -> 12 passed.

## Premium scene rendering and customer-visible copy pass

Completed on 2026-07-05:

- PPTX rendering was upgraded from a conservative small-image layout to a stronger customer-demo composition: larger right-side hero visual window, more visible depth layers, expanded reading vignette, and page-purpose-specific card systems for cover, agenda/framework, evidence/insight, process, recommendation, and conclusion slides.
- The renderer still preserves the show-safe constraints: foreground text/card boxes remain inside the slide safe area, native PowerPoint autofit remains enabled, and PPTX/HyperFrames still render from the same canonical `SlideDeck JSON`.
- Image Agent planning now varies image type by slide purpose for business decks: cover/conclusion can use product showcase, evidence/insight can use data visuals, framework/agenda can use concept/icon illustrations, and process/business slides can use business-scene visuals.
- Customer-visible copy hygiene was hardened again. The PPTX/HTML render path now strips outline scaffolding, internal planning labels, and source-metadata fragments such as encyclopedia/market-code titles (`English: ...`, `OTC Pink`, `LKNCY`) from visible slide cards.
- Topic research relevance for specific brand topics was tightened so weakly related scholarly/publication results are filtered out instead of being pulled into a brand deck as false evidence.
- The local/free image fallback was upgraded to richer deterministic PNG scenes with layered gradient backgrounds, glass panels, business/product/data/thesis-specific forms, and cinematic light/depth overlays. Real web images are still preferred when open/licensed search succeeds.
- Final web-backed customer-demo artifact: `D:\Codex\Outputs\ai-ppt-premium-scene-final-web-20260705070016`. It was re-rendered from a web-researched Luckin project and cached real/open image assets, using the latest renderer and visible-copy filter.
- Final demo QA:
  - `qualityPassed=true`, 8 slides, 8 image-plan items.
  - Public research mode was `web`, providers `wikipedia,crossref`; OpenAlex was unavailable, so the pipeline added a research-gap logic brief.
  - PowerPoint 16.0 opened `deck.pptx`, accepted SlideShowSettings 1-8, and exported 8/8 slides to PNG.
  - Exported contact sheet: `D:\Codex\Outputs\ai-ppt-premium-scene-final-web-20260705070016\powerpoint-open-test\contact-sheet.png`.
  - Backend verification: `.venv\Scripts\python.exe -m pytest apps/api/tests -q` -> 280 passed.

## Legal low-cost agent architecture and mode layering

Completed on 2026-07-06:

- Product strategy was corrected away from “use frontend subscriptions as API.” The project now treats itself as workflow/intelligent-agent software with legal low-cost architectures:
  - user-owned API keys / BYOK;
  - hybrid model routing;
  - human-in-the-loop prompt workspace where users manually copy/paste prompts into their own ChatGPT/Claude/Gemini web memberships.
- Explicit red lines were added to product specs: do not automate consumer-web login, do not collect/share/replay cookies, and do not treat ChatGPT/Claude/Gemini frontend subscriptions as backend APIs.
- Added backend `agent_modes` policy service exposing:
  - `fast` mode: lowest cost, quick loop, bounded or disabled research, cheap/local/fallback models first;
  - `research` mode: public-source cascade, source-gap brief, mid-tier routing, selective stronger QA;
  - `enterprise` mode: BYOK/customer-owned enterprise providers, stronger final polish, strict audit trail, and human review hooks.
- Added runtime settings:
  - `AI_PPT_DEFAULT_AGENT_MODE=fast|research|enterprise`;
  - `AI_PPT_DEFAULT_COST_ARCHITECTURE=byok|hybrid_router|manual_prompt_workspace`.
- `/api/runtime/status` now returns `defaultAgentMode`, `defaultCostArchitecture`, and `agentModePolicy`, including legal cost architectures, mode policies, the frontend-membership rule, and short-drama-style stage routing guidance.
- The Chinese workflow UI runtime panel now displays the three agent modes plus the three legal cost architectures so users understand the product is selling workflow and QA, not hidden model usage.
- Verification:
  - `.venv\Scripts\python.exe -m pytest apps/api/tests/test_health.py -q` -> 20 passed.
  - `.venv\Scripts\python.exe -m pytest apps/api/tests -q` -> 282 passed.
  - `pnpm --filter @ai-ppt/web typecheck` -> passed.
  - Runtime smoke confirmed `defaultAgentMode=fast`, `defaultCostArchitecture=hybrid_router`, modes `fast,research,enterprise`, and architectures `byok,hybrid_router,manual_prompt_workspace`.

## Three-tier execution modes wired into the PPT workflow

Completed on 2026-07-06:

- `ProjectBrief` now stores `agentMode=fast|research|enterprise`, with `research` as the default for legacy and new projects.
- The product default was intentionally moved from `fast` to `research` so a normal website run targets the enterprise PPT baseline instead of a low-cost draft.
- Backend execution policy now changes real workflow behavior:
  - `fast`: bounded public research, short timeouts, standard quality profile, low-cost preview posture.
  - `research`: deeper public-source cascade, web-first image resolution, enterprise PPT quality profile, source-grounded outline and premium visual-direction prompt rules.
  - `enterprise`: maximum bounded research depth, web-first image resolution, enterprise PPT quality profile, BYOK/customer-owned provider posture, and human review hooks.
- `/outline/generate`, `/visual-directions/generate`, `/render`, and `/quality/check` now resolve the project agent mode and return `agentMode` plus the concrete `executionPolicy`.
- Research mode now raises topic research to at least 7 sources / 10 seconds, raises image search to at least 7 seconds, and applies `enterprise_ppt` quality gates.
- Quality checking now includes an `enterprise_ppt_baseline` gate for research/enterprise projects. It requires PPTX/HTML existence, PowerPoint-native scaffold, per-slide visuals, Image Agent plan markers, page-plan markers, explainer layers, text autofit, safe foreground bounds, visible-copy hygiene, encoding integrity, HyperFrames motion, composition diversity, and explanation-mode diversity.
- The Chinese `/workflow` UI now includes a generation-layer selection step with three modes. Research mode is selected by default and is displayed in the final brief summary before generation.
- TypeScript/Python contracts and schema artifacts were updated so frontend and backend share the same `agentMode` project contract.
- Verification:
  - Python compile check for changed backend modules passed.
  - `.venv\Scripts\python.exe -m pytest apps\api\tests\test_health.py apps\api\tests\test_outline_api.py apps\api\tests\test_render_api.py apps\api\tests\test_quality_api.py tests\test_contract_examples.py -q` -> 101 passed.
  - `.venv\Scripts\python.exe -m pytest apps\api\tests -q` -> 282 passed.
  - `pnpm --filter @ai-ppt/web typecheck` -> passed.
  - `pnpm --filter @ai-ppt/web build` -> passed.

## Competition-grade PPT quality gates and Chinese case-outline upgrade

Completed on 2026-07-06:

- Added strict competition-grade quality gates for research/enterprise PPT runs:
  - `competition_story_arc`: cover -> agenda/context/framework/evidence/insight/recommendation -> conclusion, with no repeated title claims.
  - `competition_copy_density`: short titles, bounded card count, bounded visible copy, and no bloated slide text.
  - `competition_visual_variety`: enough distinct composition archetypes, image treatments, and motion presets across the deck.
  - `competition_image_intent`: every slide must have a content-serving image plan, distinct search intent, and non-decorative purpose.
  - `competition_ppt_baseline`: aggregate gate for strategic story, readable copy, varied page design, and content-serving image planning.
- `enterprise_ppt_baseline` now includes the competition-grade gate, so research/enterprise output cannot pass quality if it is merely a templated or weakly structured deck.
- The Image Agent search-query builder now includes slide title, key point, visual brief, and purpose so each slide gets a distinct image-search/generation intent even in local fallback mode.
- Added a Chinese case-section parser for user-provided business/case-competition material. It recognizes sections such as `背景`, `核心问题`, `关键证据`, `洞察`, `建议`, and `结论`, then maps them into a strategic PPT story instead of copying long source sentences into titles.
- The deterministic no-API fallback now turns a Luckin-style case brief into higher-quality page titles such as:
  - `危机后信任修复`
  - `作用机制：增长飞轮`
  - `关键证据：产品 × 渠道 × 用户`
  - `单点营销不是复兴`
  - `落地路径：会员、品类、供应链`
  - `结论：信任修复与数字效率`
- Added regression coverage so Chinese case-competition outlines cannot regress to titles like `作用机制：一、背景...` or weak generic filler.
- Latest validated competition-grade smoke artifact:
  - `D:\Codex\Outputs\ai-ppt-competition-grade-qa-20260706073216\deck.pptx`
  - `D:\Codex\Outputs\ai-ppt-competition-grade-qa-20260706073216\hyperframes.html`
  - `D:\Codex\Outputs\ai-ppt-competition-grade-qa-20260706073216\summary.json`
  - `D:\Codex\Outputs\ai-ppt-competition-grade-qa-20260706073216\quality-report.json`
- Final smoke result for the artifact above:
  - `qualityPassed=true`.
  - 8 slides in `SlideDeck JSON`, 8 slides in PPTX, 8 PPTX media assets, 8 slide relationship parts.
  - No replacement-character / question-mark / mojibake markers found in PPTX slide XML.
  - Competition checks all passed: story arc, copy density, visual variety, image intent, competition baseline, enterprise baseline.
  - PowerPoint COM opened `deck.pptx`, counted 8 slides, and exposed `SlideShowSettings`.
- Verification:
  - `.venv\Scripts\python.exe -m pytest apps\api\tests\test_outline_api.py -q` -> 17 passed.
  - `.venv\Scripts\python.exe -m pytest --basetemp D:\Codex\Workspaces\ai-ppt-strict-qa-20260706\pytest-final -q` -> 329 passed.
  - `pnpm --filter @ai-ppt/web typecheck` -> passed.
  - `pnpm --filter @ai-ppt/web build` -> passed.

## Customer-facing studio UI and delivery quality loop

Completed on 2026-07-07:

- `/workflow` was redesigned from a backend-like operations dashboard into a simpler customer-facing PPT generation studio.
- The visible hero now presents a dynamic `PPT 生成影棚` preview with depth, sheen, floating slide motion, and a concise promise: customers should see reliable outline, premium visuals, and playable files; model chains and image/provider details are folded away.
- Runtime/API/model/provider configuration, design benchmarks, SourcePack reading reports, page-by-page design plans, image-agent asset results, and generation logs are now collapsed behind professional/backstage detail panels instead of occupying the default customer path.
- Visual direction cards were simplified: they show preview, style name, mood, and compact design/motion/image tags instead of exposing long Frontend-Slides/HyperFrames implementation fields.
- Download state was simplified to preview/download actions first; detailed page plans and image-asset provenance are available only on demand.
- Backend quality checking now includes `customer_delivery_readiness`, an aggregate gate requiring safe PPTX, HyperFrames motion, real/generated visuals, clean copy, encoding integrity, competition baseline, award-grade design contract, and research delivery contracts.
- `/quality/check` now returns a `closedLoop` object. Passing decks return `ready`; failing decks return `repair_required`, failed checks, recommended repair actions, and `blocksExport=true`.
- The frontend now stops before export when quality fails and shows a clean repair panel with one-click image/layout refresh actions, instead of attempting to download non-deliverable files.
- Public GitHub Pages deployment was refreshed in repo `shuhongguo56-crypto/ai-ppt-agent`, commit `b60ea5d`.
- `/live/` was preserved as a redirect to the current `/workflow/` page with the active Cloudflare quick-tunnel API.
- Public link:
  - `https://shuhongguo56-crypto.github.io/ai-ppt-agent/workflow/?api=https%3A%2F%2Fenergy-flower-vacancies-commander.trycloudflare.com&v=b60ea5d`
- Verification:
  - `apps/api/tests/test_quality_api.py` -> 7 passed.
  - `pnpm --filter @ai-ppt/web typecheck` -> passed.
  - `pnpm --filter @ai-ppt/web build` -> passed.
  - `apps/api/tests` -> 295 passed.
  - `tests` -> 46 passed.
  - Public page contains the new studio UI markers: `PPT 生成影棚预览`, `客户只需要看到`, and `专业设置`.
  - Public API health passed through the Cloudflare tunnel.
  - Public end-to-end smoke `public-client-polish-smoke-1783389381` passed: 6 visual directions, 8 slides, 8 image assets, `qualityPassed=true`, `closedLoop=ready`, `customer_delivery_readiness=passed`, and exports available for both `pptx` and `hyperframes_html`.

## Canonical deck automatic repair and completed-delivery UI

Completed on 2026-07-14:

- Added `POST /api/projects/{project_id}/slide-deck/repair`. It consumes the current failed quality report, verifies the report/render/deck versions match, and writes a new confirmed canonical `SlideDeck JSON` checkpoint.
- Deterministic repair passes now address visible-copy density, title/body/card length, duplicate visible blocks, safe page composition, motion variety, explanation-mode variety, and page-specific image search/generation intent without inventing claims outside the confirmed outline.
- The frontend quality-failure action now runs up to two closed-loop repair rounds: canonical deck repair -> Image Agent resolution -> PPTX/HyperFrames render -> quality check -> export only after passing.
- The completed customer view now collapses the full questionnaire into a compact sticky task summary, keeping preview and download actions as the primary focus. Long Chinese/English titles and mobile widths were browser-verified without horizontal overflow.
- GitHub Pages deployment was refreshed in `shuhongguo56-crypto/ai-ppt-agent`, commit `5cfa26c`.
- Current public frontend: `https://shuhongguo56-crypto.github.io/ai-ppt-agent/workflow/`.
- Current public live entry (free API tunnel): `https://shuhongguo56-crypto.github.io/ai-ppt-agent/live/`.
- Verification:
  - 343 Python tests passed across API, contracts, persistence, source parsing, research, model routing, image agent, rendering, quality, and exports.
  - Next.js typecheck and production/static-export builds passed.
  - Browser E2E passed with 8 outline slides, 6 visual directions, 43/43 quality checks, editable PPTX download, HyperFrames HTML download, and online preview.
  - Desktop completed-state and 390px mobile viewport checks reported no horizontal overflow.

## Page-specific visual asset uniqueness gate

Completed on 2026-07-14:

- Final visual resolution now hashes the real image bytes for every slide, not merely the provider URL or search query.
- When a searched/generated asset duplicates an earlier slide, the Image Agent requests up to three page-specific alternatives with deliberately different camera angle, subject arrangement, depth balance, lighting, and material emphasis.
- Every generated alternative is re-hashed before acceptance. A provider cannot return the same image repeatedly and still be treated as a successful replacement.
- Asset sidecars now persist `contentHash` for auditability while the quality gate independently recomputes the hash from the actual file.
- Added `visual_asset_uniqueness` to the research/enterprise baseline and customer-delivery readiness contract. Reused, missing, unreadable, or empty slide images now block export and trigger the existing image refresh/repair loop.
- Verification:
  - Render/quality focused tests: 34 passed, including repeated-provider-output recovery and duplicate-binary rejection.
  - Full Python regression: 346 passed.
  - Next.js typecheck passed.
  - Next.js production build passed.
  - Real-image workflow artifact: `D:\Codex\Outputs\ai-ppt-real-images-20260714234337`.
  - The real workflow produced 8 slides, 8 distinct PPTX media assets, 1 Wikipedia/Wikimedia asset, 7 Pollinations FLUX assets, and passed all 44 checks including `visual_asset_uniqueness`, `customer_delivery_readiness`, and `enterprise_ppt_baseline`.
  - The public API was restarted on the current Cloudflare tunnel and returned HTTP 200 with research mode, open-web image search, and free image generation ready.

## Apple-style customer workflow interaction pass

Completed on 2026-07-15:

- Installed and applied the `apple-design` skill to the customer-facing `/workflow` experience without changing the canonical SlideDeck generation contract.
- Replaced duplicate page navigation with one floating workspace bar that continuously shows the current workflow stage and generation-service status.
- Simplified the opening message to one customer outcome, one short explanation, and one progressive question at a time.
- Removed decorative infinite aurora, sheen, slide-float, and orbit animations. Status pulses remain only where they communicate active work or connection state.
- The PPT studio preview now supports direct pointer manipulation, pointer capture, live 1:1 tilt, momentum projection, and an interruptible return animation that starts from the current on-screen transform.
- Added immediate press feedback, 44px minimum interactive targets, calmer material hierarchy, optical typography, and non-uppercase Chinese form labels.
- Added explicit `prefers-reduced-motion`, `prefers-reduced-transparency`, and `prefers-contrast` behavior.
- Added progressive auto-scroll to the next revealed chat question while respecting reduced-motion preferences.
- Fixed a mobile min-content sizing bug discovered during screenshot QA: single-column grids now use `minmax(0, 1fr)`, so titles, fields, and button labels remain inside a 390px viewport. Only the stage rail intentionally scrolls horizontally.
- Verification:
  - Next.js typecheck passed.
  - Next.js production/static export build passed.
  - Desktop and 390x844 browser checks passed with no document overflow.
  - Pointer-grab and release transforms changed continuously and returned to the resting transform after release.
  - Progressive question reveal passed.
  - Reduced-motion browser reported the materialization animation at effectively zero duration.
  - Visual QA screenshots: `D:\Codex\Outputs\ai-ppt-apple-design-20260715\desktop.png` and `mobile-fixed.png`.
  - GitHub Pages deployment commit: `50e3f18`.
  - Public workflow: `https://shuhongguo56-crypto.github.io/ai-ppt-agent/workflow/?v=45368e9`.
  - Public 390px browser verification passed with the generation service connected, 366px workflow shell, both main cards ending at x=378, and zero document-level horizontal overflow.

## Content depth, page-rhythm, and visual-choice quality pass

Completed on 2026-07-15:

- Research and enterprise modes can now supplement a user-supplied SourcePack with public research instead of skipping research whenever a file or pasted text exists. The user's material remains first in source order and supplemental sources are deduplicated.
- Public-source retrieval now applies strict relevance filtering to long Chinese topics. Irrelevant scholarly results are rejected; an explicit local evidence-gap brief is safer than contaminating a deck with an unrelated paper.
- Fixed a broad retail classifier that treated any topic containing “品牌” as a Luckin/coffee case. Retail fallback now requires a named Luckin case or multiple actual retail markers.
- Removed internal planning scaffolds such as “封面直接给出主题” and “结尾页回到原文主旨” from customer-visible outline claims.
- Added a source-grounded business storyline fallback with distinct jobs for context, mechanism, evidence boundary, insight, strategic priorities, success metrics, and conclusion. Adjacent pages no longer paraphrase one thesis repeatedly.
- Canonical page planning now enforces anchor/dense/breathing rhythm, adjacent archetype/treatment changes, and unique composition signatures. The PPTX renderer has visibly different agenda, framework, evidence, insight, recommendation, and conclusion geometries while keeping text and image safe zones separate.
- The final visual-direction selector now shows only the preview, direction name, palette, and selection action. Repeated direction copy and long mood/implementation text were removed. Preview frames use explicit aspect ratios, clipping, min-width safety, and mobile containment.
- Browser QA passed at 1440px and 390px: six direction cards stayed inside the grid/viewport, every preview stayed inside its card, document horizontal overflow was zero, and no console or network errors were recorded.
- Delivery QA project `qa-delivery-20260715130540` produced 8 page-specific composition variants, 8 visual assets, editable PPTX, HyperFrames HTML, and a 44/44 `ready` quality result.
- QA artifacts: `D:\Codex\Outputs\ai-ppt-final-qa-20260715-v2` and `D:\Codex\Outputs\ai-ppt-ui-qa-20260715`.
- Verification: 347 Python tests passed and the Next.js production build passed.

## Semantic image sourcing and visible-text rejection

Completed on 2026-07-18:

- Image resolution now ranks licensed Openverse results by page-specific query relevance before downloading them.
- Chinese electric-vehicle topics use slide-intent-specific English scene queries for competition, customer, growth, strategy, and organization pages instead of repeating one generic topic query.
- Web and generated image candidates now pass an optional local Tesseract OCR gate. Images carrying excessive signage, labels, watermarks, or pseudo-typography are rejected before PPTX/HTML rendering.
- Openverse metadata carrying explicit sign/logo/poster/branding risk is rejected before download.
- Pollinations negative prompts and every supported image-type prompt forbid text, numbers, logos, watermarks, interfaces, documents, and slide-like imagery.
- Free image generation retries only pages that remain unresolved, at reduced concurrency, before the deterministic local fallback.
- Cached deterministic placeholder assets are ignored during automatic refresh so a later run can upgrade them to licensed or generated visuals.
- Public API restarted with cascade text routing, open-web image search, Pollinations FLUX fallback, three image workers, two recovery rounds, and OCR enabled.
- Current public API: `https://ctrl-trials-europe-radar.trycloudflare.com`.

## Self-healing public entry

- `scripts/public-runtime.ps1` keeps the free local FastAPI/PPT engine and Cloudflare quick tunnel reachable through one permanent GitHub Pages entry.
- The script starts the API when needed, reuses a healthy tunnel, creates a replacement tunnel after a disconnect, and updates only `live/index.html` on the Pages branch through the authenticated GitHub CLI.
- Runtime state and logs are stored under `D:\Codex\Workspaces\ai-ppt-public-runtime`; no provider keys are committed.
- The intended Windows scheduled task runs the supervisor every five minutes, so reconnects do not require the customer-facing URL to change.
- Verification: 357 Python tests passed; Next.js production build and typecheck passed; Git diff whitespace validation passed.

## Visual-selection fetch recovery

- Fixed a public workflow failure where a brief tunnel interruption after visual-direction selection surfaced as the raw browser message `Failed to fetch` even though the selected direction and canonical SlideDeck had already been saved.
- Customer-facing API requests now retry transient network and Cloudflare 5xx failures with bounded backoff.
- Visual selection and SlideDeck assembly are idempotent, so retrying a request whose response was lost resumes the same checkpoint instead of creating a conflicting version.
- The workflow stores the confirmed visual and assembled SlideDeck in client state immediately, before the slower Image Agent phase begins.
- The public FastAPI runtime was restarted without changing its established database/assets; the affected latest project remained available and its stale-version retry returned the existing selected direction and 8-slide deck successfully.
- GitHub Pages was rebuilt and deployed with the recovery client.

## Quality-repair prompt and visual-asset recovery

- Fixed the quality repair loop truncating image prompts from the right at 360 characters. The truncation removed the required `award-winning` and `single focal` clauses, so a deck that initially passed the award-grade contract could fail every later repair.
- Repaired prompts now keep a bounded page-specific semantic body and always append one canonical award-grade image contract exactly once. Repeated repair passes no longer grow the prompt or remove QA clauses.
- When search/free generation is temporarily unavailable, the Image Agent now searches earlier SlideDeck versions from the same project and reuses only a real JPEG/PNG from the same slide, image type, and exact semantic purpose. It copies the asset into the current render, rejects duplicates and OCR-risk images, preserves attribution, and still refuses vector placeholders at the delivery gate.
- Corrected the public runtime environment names to `AI_PPT_IMAGE_RESOLUTION_WORKERS` and `AI_PPT_IMAGE_GENERATION_RETRY_ROUNDS` so the intended two-worker/three-retry policy is actually applied.
- Failed project `demo-1784386400321` was repaired to SlideDeck v6. Slide 8 recovered the prior accepted Pollinations image instead of `safe_vector_fallback`; all 8 images are distinct JPEG assets.
- Final quality result: 44/44 passed, including `visual_asset_source_quality`, `award_grade_design_contract`, `competition_ppt_baseline`, `customer_delivery_readiness`, `enterprise_ppt_baseline`, and `visual_asset_uniqueness`.
- Verification: 361 Python tests passed, TypeScript typecheck passed, and Git whitespace validation passed.
