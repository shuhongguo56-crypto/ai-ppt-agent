# Open-source AI PPT layout research

Updated: 2026-07-19

## Primary projects reviewed

- [PPTAgent](https://github.com/icip-cas/PPTAgent) and its [paper](https://arxiv.org/abs/2501.03936): infer structural patterns from reference decks, select layouts by content capacity and image relevance, then render and evaluate the artifact.
- [DeepPresenter](https://arxiv.org/abs/2602.22839): use environment-grounded reflection—plan, render, inspect the actual result, and revise—instead of assuming template coordinates are correct.
- [Presenton](https://github.com/presenton/presenton): keep one canonical 1280×720 slide component tree; rendering, editing, persistence and export consume the same structure. Its layout prompts bind text-array limits to the actual container capacity.
- [PptxGenJS](https://github.com/gitbrent/PptxGenJS): mature editable PPTX generation primitives and Office-compatible packaging.
- [Slidev](https://github.com/slidevjs/slidev) and [reveal.js](https://github.com/hakimel/reveal.js): presentation-mode HTML, keyboard control, animation and responsive stage patterns.
- [presentation-ai](https://github.com/allweonedev/presentation-ai): measured scaling and semantic layout components rather than raw absolute-position templates.
- [ppt-agent-skill](https://github.com/Akxan/ppt-agent-skill): a useful commercial layout taxonomy—single-focus, symmetric, asymmetric, three-column, primary-secondary, hero-top, mixed-grid, L-shape, T-shape and waterfall—with explicit page-to-page rhythm rules.

## Contracts adopted in this repository

1. `OutlineDecision -> SlideDeck JSON` remains the single content source. PPTX and HyperFrames do not invent independent copy.
2. Content capacity is a layout input. Text boxes reserve SimSun line height and must fit before rendering; clipping is not accepted as a design technique.
3. Image relevance is evaluated per page. The Image Agent may use a full-bleed image, a window, a strip or an atmospheric layer depending on the page job; it is not forced to the right.
4. A deck uses one design grammar but several visual gravity fields. Adjacent pages should change at least two of image position, content axis, density, scale or boundary treatment.
5. Rendered-artifact reflection is mandatory for customer delivery: export PPTX, open/render it through a real Office engine, inspect slide images, then run machine quality gates.
6. Binary image uniqueness is a hard gate. If a provider repeats bytes, that result is unresolved and must be regenerated or recovered from a semantically identical prior version before export.

## Low-cost batch path

The fastest low-cost path is not “more templates.” It is a bounded pipeline:

`source-grounded outline -> page job classification -> capacity-matched layout family -> page-specific image search -> free image generation only for gaps -> canonical SlideDeck -> two renderers -> Office/HTML visual inspection -> targeted repair`

Cheap models can handle extraction, classification and structured transformation. Stronger models are reserved for research synthesis, storyline judgment and final editorial repair. Image search runs before generation, and only unresolved pages consume image-generation capacity.
