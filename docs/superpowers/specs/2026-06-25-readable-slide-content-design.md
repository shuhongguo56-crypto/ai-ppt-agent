# Readable Slide Content and Explainer Layout Design

## Problem statement

The 2026-06-24 topic-only smoke deck proves that sources, images, explainer plans, and both export formats are connected. Visual inspection in PowerPoint exposes a second-order defect: source-grounded fallback content contains internal planning labels (`第 N 页`, `原文线索`, `页面作用`, `可引用证据`), while `diagramLabels` copies those long strings and the PPTX renderer repeats them in a fixed-height bottom overlay. On slide 3, seven of ten text boxes overflow; on slide 5, all four repeated explainer cards overflow.

## Goal

Produce natural visible slide copy and readable explanatory visuals without breaking the invariant that all claims come from the confirmed outline and both PPTX/HTML share one canonical `SlideDeck JSON`.

## Chosen approach

Fix the problem at all three ownership boundaries:

1. HumanizePPT local source-grounded fallback emits audience-facing copy, not workflow commentary. Speaker notes may retain provenance guidance, but slide titles, key points, and talking points may not expose internal planning labels.
2. SlideDeck assembly derives two to four concise diagram labels from outline content. Labels remain traceable substrings or clause-level reductions of the confirmed outline and obey a display budget.
3. PPTX rendering no longer duplicates all explainer labels as bottom cards. It keeps a `Page Explainer` marker and renders mode-specific editable geometry that relates the existing outline-derived content blocks. Text boxes use native PowerPoint autofit.
4. HyperFrames keeps its shared explainer layer, but uses the concise canonical labels and a maximum of three visible nodes to avoid collisions.

## Quality requirements

- Visible slide content must not contain `第 N 页`, `Slide N:`, `原文线索`, `Source claim`, `页面作用`, `Slide role`, `可引用证据`, or `Useful excerpt`.
- `diagramLabels` contains 2–4 items; each item is at most 32 CJK characters or 64 Latin characters.
- PPTX explainer geometry contains no duplicate long-form text cards.
- PPTX card and general text shapes declare native autofit behavior.
- Decks retain one explainer marker and one image asset per slide.
- Rendered slides must be re-exported to PNG and inspected for overflow after automated tests pass.

## Non-goals

- Replacing the entire OOXML renderer.
- Adding authentication, billing, or production hosting.
- Inventing new facts, metrics, or citations outside the outline/SourcePack.
