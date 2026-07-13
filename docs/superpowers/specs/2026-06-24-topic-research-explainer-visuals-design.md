# Topic Research and Explainer Visuals Design

## Goal

When a user supplies only a topic, the product must research public web sources before generating the outline. Every generated slide must then pair its outline-derived message with a content-explaining visual layer, rather than using an unrelated decorative background.

## Product behavior

1. A supplied `SourcePack` remains authoritative and skips automatic topic research.
2. If no sources are supplied, the API searches a bounded provider cascade: Wikipedia for an accessible topic overview, then OpenAlex and Crossref for evidence-oriented publications.
3. Retrieved results are normalized into the existing `SourcePack` contract with stable source IDs, titles, URLs, a thesis, key claims, evidence notes, suggested PPT flow, and excerpts.
4. Network failure never blocks the workflow. A clearly labelled local research fallback still creates a SourcePack, while the API reports that live retrieval was unavailable.
5. The outline response returns the effective `SourcePack` and research metadata so the Chinese workflow UI can show exactly what was read before outline review.
6. Every `SlideDesignPlan` includes an explanation mode, a slide-specific visual brief, and 2–6 diagram labels derived only from that outline slide.
7. PPTX and HyperFrames HTML consume those same explanation fields. Both outputs include a visible explanatory layer (diagram, process, evidence, comparison, annotated image, or summary map) in addition to the page image.

## Architecture

- `services/research.py` owns network retrieval, normalization, limits, and fallback behavior. The outline route only decides whether research is needed.
- The canonical SlideDeck contract owns explainer intent. Renderers do not invent slide meaning; they translate the plan into editable PPTX shapes and an animated HTML layer.
- Quality checks validate explainer coverage and mode diversity in both formats.

## Safety and quality boundaries

- Only public HTTPS endpoints are queried; requests have short timeouts, response limits, and an explicit user agent.
- Search results are capped and deduplicated. Raw HTML is never injected into the deck or UI.
- Source URLs and provider names remain traceable.
- A diagram label must come from the slide title, key point, or talking points; renderer-only filler is forbidden.
- A six-slide-or-longer deck must use at least three explanation modes.
