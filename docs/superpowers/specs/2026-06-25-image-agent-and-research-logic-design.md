# Image Agent and Research Logic Design

## Goal

Make PPT generation stop treating images as late decorative fallbacks. Every deck must first produce a source-grounded visual asset plan, then render PPTX and HyperFrames HTML from that plan. Topic-only research must also form a clearer logic chain instead of stitching incomplete search snippets together.

## Scope

- Add an `Image Agent` planning layer to canonical `SlideDeck JSON`.
- Keep PPTX and HyperFrames HTML rendered from the same `SlideDeck JSON`.
- Keep image providers replaceable: OpenAI Image API, Midjourney API, Stable Diffusion API, and custom image2-compatible providers can fit behind the existing image gateway boundary.
- Improve public-source synthesis so the outline sees a clear narrative chain: central question, why now, mechanism, evidence, risk, recommended action.

## Data contract

Add `ImagePlanItem` to the slide-deck contract:

- `slide`: slide index.
- `needsImage`: whether the slide needs a visual asset. Current product policy sets this to true for every generated slide.
- `imageType`: `background`, `course_review_atmosphere`, `business_scene`, `classical_element`, `thesis_concept`, `product_showcase`, `icon_illustration`, or `data_visual`.
- `prompt`: content-grounded image prompt.
- `purpose`: why the image exists on this slide.
- `searchQuery`: concise query for open web / licensed asset retrieval.
- `providerChain`: ordered adapters to try.

The API response will expose this as `slideDeck.imagePlan`. Internally the Python field is `image_plan`. This preserves the existing camelCase contract style while representing the user-requested `image_plan` module.

## Flow

1. HumanizePPT creates `OutlineDecision`.
2. Frontend-Slides creates three directions.
3. SlideDeck assembly creates page design plans and calls Image Agent planning.
4. Render resolves visual assets strictly from `deck.imagePlan`.
5. Quality gates verify the image plan exists, covers every slide, and is referenced by both PPTX and HTML outputs.

## Research logic

Public-source synthesis should no longer be a loose source list. It should add a synthesis source with:

- central question;
- why-now context;
- mechanism;
- evidence map;
- risk / limitation;
- audience-specific action;
- recommended PPT flow.

For the AI + higher-education topic, this produces a deck logic around teaching design, learning support, assessment integrity, governance, and implementation actions.

## Non-goals

- Do not add billing, auth, or production storage in this pass.
- Do not require a real image2 key. If no provider key exists, local fallback still works but must preserve the image plan and provider-chain metadata.
