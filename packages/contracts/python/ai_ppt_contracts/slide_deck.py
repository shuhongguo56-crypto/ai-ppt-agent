from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from .base import ContractModel, NonBlankString
from .outline import DeckLanguage, SlidePurpose
from .visual import VisualDirectionId


SlideBlockType = Literal["headline", "subtitle", "body", "card", "chart_placeholder", "image_placeholder", "speaker_notes"]
CompositionArchetype = Literal[
    "cinematic_hero",
    "editorial_cover",
    "architectural_cover",
    "chapter_index",
    "editorial_split",
    "diagonal_story",
    "statement_focus",
    "proof_mosaic",
    "data_landscape",
    "process_ribbon",
    "system_map",
    "split_comparison",
    "priority_stack",
    "closing_echo",
    "manifesto_close",
    "future_horizon",
]
ImageTreatment = Literal[
    "full_bleed",
    "split_crop",
    "masked_window",
    "layered_cutout",
    "evidence_strip",
    "atmospheric_backdrop",
]
AssetRole = Literal["hero", "context", "evidence", "diagram", "metaphor", "portrait"]
ContentDensity = Literal["sparse", "balanced", "dense"]
ImageAssetType = Literal[
    "background",
    "course_review_atmosphere",
    "business_scene",
    "classical_element",
    "thesis_concept",
    "product_showcase",
    "icon_illustration",
    "data_visual",
]
ImageProviderAdapter = Literal[
    "open_web_search",
    "OpenAI Image API",
    "Pollinations FLUX API",
    "Midjourney API",
    "Stable Diffusion API",
    "custom image2 API",
    "local_png_fallback",
]
MotionPreset = Literal[
    "cinematic_reveal",
    "editorial_wipe",
    "depth_parallax",
    "evidence_reveal",
    "sequence_build",
    "diagram_orbit",
    "closing_resolve",
]
ExplanationMode = Literal[
    "hero_photo",
    "concept_diagram",
    "process_diagram",
    "data_evidence",
    "comparison_visual",
    "annotated_image",
    "summary_map",
]
DiagramLabel = Annotated[str, StringConstraints(min_length=1, max_length=64, pattern=r"\S")]


class SlideDeckTheme(ContractModel):
    direction_id: VisualDirectionId
    name: NonBlankString
    palette: list[NonBlankString] = Field(min_length=3, max_length=8)
    typography: NonBlankString
    texture_layer: NonBlankString
    layout_principles: list[NonBlankString] = Field(min_length=3, max_length=8)
    design_system_id: NonBlankString
    design_seed: int = Field(ge=0, le=2_147_483_647)


class SlideBlock(ContractModel):
    block_id: NonBlankString
    block_type: SlideBlockType
    content: NonBlankString
    role: NonBlankString


class SlideDesignPlan(ContractModel):
    composition_archetype: CompositionArchetype
    composition_variant: NonBlankString
    image_treatment: ImageTreatment
    asset_role: AssetRole
    asset_query: NonBlankString
    content_density: ContentDensity
    hierarchy: list[NonBlankString] = Field(min_length=3, max_length=8)
    visual_layers: list[NonBlankString] = Field(min_length=3, max_length=8)
    explanation_mode: ExplanationMode
    visual_brief: NonBlankString
    diagram_labels: list[DiagramLabel] = Field(min_length=2, max_length=4)
    motion_preset: MotionPreset
    rationale: NonBlankString


class ImagePlanItem(ContractModel):
    slide: int = Field(ge=1)
    needs_image: bool
    image_type: ImageAssetType
    prompt: NonBlankString
    purpose: NonBlankString
    search_query: NonBlankString
    provider_chain: list[ImageProviderAdapter] = Field(min_length=1, max_length=7)


class SlideDeckSlide(ContractModel):
    slide_id: NonBlankString
    slide_index: int = Field(ge=1)
    title: NonBlankString
    subtitle: str | None = None
    purpose: SlidePurpose
    layout: NonBlankString
    visual_intent: NonBlankString
    design_plan: SlideDesignPlan
    blocks: list[SlideBlock] = Field(min_length=2, max_length=12)
    speaker_notes: NonBlankString


class SlideDeck(ContractModel):
    project_id: NonBlankString
    outline_version: int = Field(ge=1)
    visual_direction_version: int = Field(ge=1)
    language: DeckLanguage
    title: NonBlankString
    theme: SlideDeckTheme
    slides: list[SlideDeckSlide] = Field(min_length=3, max_length=30)
    image_plan: list[ImagePlanItem] = Field(min_length=3, max_length=30)
    export_targets: list[Literal["pptx", "hyperframes_html"]] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def enforce_deck_invariants(self) -> "SlideDeck":
        indexes = [slide.slide_index for slide in self.slides]
        if indexes != list(range(1, len(self.slides) + 1)):
            raise ValueError("slide_index values must be continuous from 1")
        if self.export_targets != ["pptx", "hyperframes_html"]:
            raise ValueError("export_targets must be pptx and hyperframes_html")
        if len({slide.slide_id for slide in self.slides}) != len(self.slides):
            raise ValueError("slide_id values must be unique")
        image_plan_indexes = [item.slide for item in self.image_plan]
        if image_plan_indexes != indexes:
            raise ValueError("image_plan must contain exactly one item per slide in slide order")
        if any(not item.needs_image for item in self.image_plan):
            raise ValueError("every generated slide currently requires an image plan item")
        if any("decorative" in item.purpose.lower() for item in self.image_plan):
            raise ValueError("image plan purposes must describe content service, not decoration")
        if any(
            not any(block.block_type == "image_placeholder" for block in slide.blocks)
            for slide in self.slides
        ):
            raise ValueError("every slide must include an image_placeholder block")
        archetypes = [slide.design_plan.composition_archetype for slide in self.slides]
        if any(left == right for left, right in zip(archetypes, archetypes[1:])):
            raise ValueError("adjacent slides must not reuse the same composition archetype")
        if len(self.slides) >= 6 and len(set(archetypes)) < 3:
            raise ValueError("decks with six or more slides require at least three composition archetypes")
        treatments = {slide.design_plan.image_treatment for slide in self.slides}
        if len(self.slides) >= 6 and len(treatments) < 2:
            raise ValueError("decks with six or more slides require at least two image treatments")
        explanation_modes = {slide.design_plan.explanation_mode for slide in self.slides}
        if len(self.slides) >= 6 and len(explanation_modes) < 3:
            raise ValueError("decks with six or more slides require at least three explanation modes")
        return self
