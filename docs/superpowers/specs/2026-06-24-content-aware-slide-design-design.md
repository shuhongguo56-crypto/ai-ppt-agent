# Content-Aware Slide Design Specification

## Goal

After a user selects one of the three visual directions, the system must perform a second, content-aware planning pass for every slide. It must not render a deck by applying one repeated module to different text.

## Product rules

- Every slide receives a persisted `SlideDesignPlan` inside the canonical `SlideDeck JSON`.
- The plan is derived from the selected direction, the slide purpose, actual slide text, citations, asset needs, and a deterministic project-specific design seed.
- Every slide has a visual asset role and an explicit content-grounded asset query. Every rendered PPTX and HTML frame contains one visual asset.
- Adjacent slides may not reuse the same composition archetype. A normal deck must use multiple archetypes and image treatments.
- Two projects with the same outline but different project IDs receive different design-system IDs and usually different composition selections.
- PPTX and HyperFrames HTML consume the same `SlideDesignPlan`; neither renderer invents an independent page design.

## Architecture

`VisualDirectionDecision` remains the deck-wide art-direction choice. `assemble_slide_deck` then creates a project-level design system fingerprint and one page plan per outline slide. The renderers dispatch from the page plan's composition archetype, image treatment, hierarchy, and motion preset. Quality checks inspect the canonical plan and both exported artifacts for per-page images and sufficient composition diversity.

## Page plan contract

Each slide records:

- `compositionArchetype`: a content-appropriate page skeleton such as cinematic hero, editorial split, data landscape, proof mosaic, process ribbon, system map, priority stack, or closing echo.
- `compositionVariant`: a project-seeded variant that changes alignment, emphasis, and geometry.
- `imageTreatment`: full bleed, split crop, masked window, layered cutout, evidence strip, or atmospheric backdrop.
- `assetRole` and `assetQuery`: what the image proves or contributes, grounded in the title, key point, talking points, visual intent, and requested assets.
- `contentDensity`, `hierarchy`, `visualLayers`, and `motionPreset`: explicit rendering instructions shared by PPTX and HTML.
- `rationale`: a short explanation of why the page design fits the content.

## Planning behavior

The planner uses content signals before deterministic variation. Citations and numeric language favor evidence/data layouts; sequence language favors process layouts; comparison language favors split comparison; framework content favors system maps; sparse claims favor statement pages. Purpose-specific archetype pools and a stable hash then introduce project-level variation without randomness or nondeterministic outputs.

## Rendering behavior

PPTX keeps text and design elements editable and places the page image according to the image treatment. HyperFrames exposes the same plan as data attributes and composition classes, uses different CSS geometry per archetype, and applies the selected motion preset with reduced-motion fallback.

## Quality gates

- Canonical deck: every slide has a design plan and an image placeholder.
- Diversity: no adjacent duplicate archetype; at least three archetypes and two image treatments for decks of six or more slides.
- PPTX: one image relationship per slide and page-level design markers identifying the planned archetype.
- HTML: one frame asset per slide, page-plan data attributes, multiple composition classes, motion markers, and reduced-motion support.
- Existing source-grounding, slide-count, notes, path-safety, and shared-deck checks remain mandatory.

## Error handling

Planning is deterministic and local, so it remains available when model or image providers are unavailable. Missing web imagery still follows the established search -> configured AI image -> local fallback chain, while retaining the same content-grounded asset query.

## Test strategy

Contract tests cover required page-plan fields and invariants. Assembly tests prove content-sensitive archetype selection, adjacency diversity, project-level differentiation, and per-slide assets. Render tests inspect PPTX XML and HTML attributes/classes. Quality tests require the new diversity and page-plan markers.
