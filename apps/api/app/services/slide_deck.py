from __future__ import annotations

from ai_ppt_contracts import OutlineDecision, SlideDeck, VisualDirectionDecision


def assemble_slide_deck(
    *,
    outline: OutlineDecision,
    outline_version: int,
    visual: VisualDirectionDecision,
    visual_direction_version: int,
) -> SlideDeck:
    if visual.selected_direction_id is None:
        raise ValueError("visual direction must be selected")
    selected = next(
        direction
        for direction in visual.directions
        if direction.direction_id == visual.selected_direction_id
    )
    slides = []
    for slide in outline.slides:
        blocks = [
            {
                "schemaVersion": "1.0.0",
                "blockId": f"slide-{slide.slide_index}-headline",
                "blockType": "headline",
                "content": slide.title,
                "role": "primary message",
            },
        ]
        if slide.subtitle:
            blocks.append(
                {
                    "schemaVersion": "1.0.0",
                    "blockId": f"slide-{slide.slide_index}-subtitle",
                    "blockType": "subtitle",
                    "content": slide.subtitle,
                    "role": "context",
                }
            )
        blocks.extend(
            {
                "schemaVersion": "1.0.0",
                "blockId": f"slide-{slide.slide_index}-point-{point_index}",
                "blockType": "card" if point_index <= 3 else "body",
                "content": point,
                "role": "supporting point",
            }
            for point_index, point in enumerate(slide.talking_points, start=1)
        )
        if slide.required_assets:
            blocks.append(
                {
                    "schemaVersion": "1.0.0",
                    "blockId": f"slide-{slide.slide_index}-asset",
                    "blockType": "image_placeholder",
                    "content": ", ".join(slide.required_assets),
                    "role": "asset placeholder",
                }
            )
        if slide.citation_ids:
            blocks.append(
                {
                    "schemaVersion": "1.0.0",
                    "blockId": f"slide-{slide.slide_index}-chart",
                    "blockType": "chart_placeholder",
                    "content": ", ".join(slide.citation_ids),
                    "role": "evidence placeholder",
                }
            )
        slides.append(
            {
                "schemaVersion": "1.0.0",
                "slideId": f"{outline.project_id}-slide-{slide.slide_index}",
                "slideIndex": slide.slide_index,
                "title": slide.title,
                "subtitle": slide.subtitle,
                "purpose": slide.purpose,
                "layout": slide.suggested_layout,
                "visualIntent": f"{slide.visual_intent} Direction: {selected.name}.",
                "blocks": blocks,
                "speakerNotes": slide.speaker_notes_draft,
            }
        )

    title = outline.slides[0].title
    return SlideDeck(
        schemaVersion="1.0.0",
        projectId=outline.project_id,
        outlineVersion=outline_version,
        visualDirectionVersion=visual_direction_version,
        language=outline.language,
        title=title,
        theme={
            "schemaVersion": "1.0.0",
            "directionId": selected.direction_id,
            "name": selected.name,
            "palette": selected.palette,
            "typography": selected.typography,
            "textureLayer": selected.texture_layer,
            "layoutPrinciples": selected.layout_principles,
        },
        slides=slides,
        exportTargets=["pptx", "hyperframes_html"],
    )

