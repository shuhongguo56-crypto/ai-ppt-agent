from __future__ import annotations

from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from shutil import copytree
from types import ModuleType

import pytest
from pydantic import ValidationError

from ai_ppt_contracts import (
    OutlineDecision,
    ProjectBrief,
    QualityReport,
    RenderResult,
    SlideDeck,
    SourceItem,
    SourcePack,
    VisualDirectionDecision,
    WorkflowCheckpoint,
)


ROOT = Path(__file__).resolve().parents[1]


def valid_brief(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "schemaVersion": "1.0.0",
        "projectId": "project-1",
        "inputLanguage": "zh",
        "outputLanguage": "bilingual",
        "deckType": "course_presentation",
        "topic": "How CRISPR works",
        "audience": "Undergraduate biology students",
        "mode": "professional",
    }
    values.update(overrides)
    return values


def valid_checkpoint(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "schemaVersion": "1.0.0",
        "projectId": "project-1",
        "stage": "outline",
        "status": "draft",
        "version": 1,
        "payload": {},
        "createdAt": datetime.now(timezone.utc),
    }
    values.update(overrides)
    return values


def valid_outline(**overrides: object) -> dict[str, object]:
    slide = {
        "schemaVersion": "1.0.0",
        "subtitle": None,
        "talkingPoints": ["point"],
        "visualIntent": "premium visual",
        "requiredAssets": [],
        "citationIds": [],
        "speakerNotesDraft": "speaker notes",
        "constraints": [],
    }
    values: dict[str, object] = {
        "schemaVersion": "1.0.0",
        "projectId": "project-1",
        "language": "bilingual",
        "deckType": "course_presentation",
        "audience": "Undergraduate biology students",
        "objective": "Teach the audience clearly.",
        "targetSlideCount": 3,
        "narrative": ["Frame", "Explain", "Close"],
        "slides": [
            slide
            | {
                "slideIndex": 1,
                "title": "Cover",
                "purpose": "cover",
                "keyPoint": "cover point",
                "suggestedLayout": "hero",
            },
            slide
            | {
                "slideIndex": 2,
                "title": "Evidence",
                "purpose": "evidence",
                "keyPoint": "evidence point",
                "suggestedLayout": "chart_focus",
            },
            slide
            | {
                "slideIndex": 3,
                "title": "Close",
                "purpose": "conclusion",
                "keyPoint": "closing point",
                "suggestedLayout": "closing",
            },
        ],
        "assetNeeds": [],
        "citationNeeds": [],
        "risks": [],
        "qualityScores": {"structure": 88},
        "generatedBy": {
            "schemaVersion": "1.0.0",
            "skillName": "HumanizePPT",
            "skillVersion": "1.0.0",
            "model": "gpt-5.4-mini",
            "promptHash": "sha256:9f4ea49a2e2a5204ce1eaad3c7dbeadef09674ca136a6a5e5e1a57fb9c1886",
            "generationId": "a" * 64,
            "generatedAt": datetime.now(timezone.utc),
        },
    }
    values.update(overrides)
    return values


def valid_visual_direction(**overrides: object) -> dict[str, object]:
    direction = {
        "schemaVersion": "1.0.0",
        "mood": "premium",
        "palette": ["#000000", "#FFFFFF", "#CCCCCC"],
        "typography": "clean sans",
        "layoutPrinciples": ["clear hierarchy", "strong grid", "low clutter"],
        "textureLayer": "subtle glass cards",
        "sampleSlideIntents": ["cover", "evidence", "close"],
        "riskNotes": [],
    }
    values: dict[str, object] = {
        "schemaVersion": "1.0.0",
        "projectId": "project-1",
        "outlineVersion": 2,
        "directions": [
            direction | {"directionId": "apple", "name": "Apple"},
            direction | {"directionId": "mckinsey", "name": "McKinsey"},
            direction | {"directionId": "airbnb", "name": "Airbnb"},
        ],
        "selectedDirectionId": None,
        "generatedBy": {
            "schemaVersion": "1.0.0",
            "skillName": "Frontend-Slides",
            "skillVersion": "1.0.0",
            "model": "gpt-5.4-mini",
            "promptHash": "sha256:0f2db8d7357e11480acfdc94ed0f3d13bfad30a6dfd58e120f1e3e14d435a0cb",
            "generationId": "b" * 64,
            "generatedAt": datetime.now(timezone.utc),
        },
    }
    values.update(overrides)
    return values


def valid_slide_deck(**overrides: object) -> dict[str, object]:
    slide = {
        "schemaVersion": "1.0.0",
        "subtitle": None,
        "purpose": "evidence",
        "layout": "chart_focus",
        "visualIntent": "premium visual",
        "blocks": [
            {
                "schemaVersion": "1.0.0",
                "blockId": "block-1",
                "blockType": "headline",
                "content": "Headline",
                "role": "primary",
            },
            {
                "schemaVersion": "1.0.0",
                "blockId": "block-2",
                "blockType": "body",
                "content": "Body",
                "role": "support",
            },
        ],
        "speakerNotes": "Notes",
    }
    values: dict[str, object] = {
        "schemaVersion": "1.0.0",
        "projectId": "project-1",
        "outlineVersion": 2,
        "visualDirectionVersion": 3,
        "language": "bilingual",
        "title": "Deck title",
        "theme": {
            "schemaVersion": "1.0.0",
            "directionId": "apple",
            "name": "Apple",
            "palette": ["#000", "#fff", "#ccc"],
            "typography": "clean sans",
            "textureLayer": "subtle glass",
            "layoutPrinciples": ["clear", "spacious", "focused"],
        },
        "slides": [
            slide
            | {
                "slideId": "slide-1",
                "slideIndex": 1,
                "title": "Cover",
                "purpose": "cover",
                "layout": "hero",
            },
            slide | {"slideId": "slide-2", "slideIndex": 2, "title": "Evidence"},
            slide
            | {
                "slideId": "slide-3",
                "slideIndex": 3,
                "title": "Close",
                "purpose": "conclusion",
                "layout": "closing",
            },
        ],
        "exportTargets": ["pptx", "hyperframes_html"],
    }
    values.update(overrides)
    return values


def valid_render_result(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "schemaVersion": "1.0.0",
        "projectId": "project-1",
        "slideDeckVersion": 1,
        "artifacts": [
            {
                "schemaVersion": "1.0.0",
                "target": "pptx",
                "path": "D:/Codex/Outputs/deck.pptx",
                "contentType": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                "slideCount": 3,
            },
            {
                "schemaVersion": "1.0.0",
                "target": "hyperframes_html",
                "path": "D:/Codex/Outputs/deck.html",
                "contentType": "text/html; charset=utf-8",
                "slideCount": 3,
            },
        ],
    }
    values.update(overrides)
    return values


def load_schema_exporter() -> ModuleType:
    path = ROOT / "packages" / "contracts" / "scripts" / "export_schemas.py"
    spec = spec_from_file_location("contract_schema_exporter", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_project_brief_accepts_supported_schema_and_serializes_camel_case() -> None:
    brief = ProjectBrief(**valid_brief())

    assert brief.schema_version == "1.0.0"
    assert brief.model_dump(by_alias=True) == valid_brief()


def test_contract_rejects_unknown_schema_version() -> None:
    with pytest.raises(ValidationError):
        ProjectBrief(**valid_brief(schemaVersion="2.0.0"))


def test_contract_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ProjectBrief(**valid_brief(unexpected="value"))


@pytest.mark.parametrize("topic", ["", "x" * 501])
def test_project_brief_enforces_topic_length(topic: str) -> None:
    with pytest.raises(ValidationError):
        ProjectBrief(**valid_brief(topic=topic))


@pytest.mark.parametrize("audience", ["", "x" * 501])
def test_project_brief_enforces_audience_length(audience: str) -> None:
    with pytest.raises(ValidationError):
        ProjectBrief(**valid_brief(audience=audience))


def test_project_brief_rejects_empty_project_id() -> None:
    with pytest.raises(ValidationError):
        ProjectBrief(**valid_brief(projectId=""))


def test_source_pack_and_checkpoint_require_versions() -> None:
    with pytest.raises(ValidationError):
        SourcePack(projectId="project-1", sources=[])

    with pytest.raises(ValidationError):
        WorkflowCheckpoint(
            projectId="project-1",
            stage="outline",
            status="draft",
            version=1,
            payload={},
            createdAt=datetime.now(timezone.utc),
        )


def test_source_pack_uses_isolated_default_source_lists() -> None:
    first = SourcePack(schemaVersion="1.0.0", projectId="one")
    second = SourcePack(schemaVersion="1.0.0", projectId="two")
    first.sources.append(
        SourceItem(
            schemaVersion="1.0.0",
            sourceId="source-1",
            sourceType="text",
            summary="A summary",
        )
    )

    assert second.sources == []


def test_workflow_checkpoint_enforces_positive_version() -> None:
    with pytest.raises(ValidationError):
        WorkflowCheckpoint(**valid_checkpoint(version=0))


def test_workflow_checkpoint_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError):
        WorkflowCheckpoint(**valid_checkpoint(createdAt=datetime(2026, 6, 20, 12, 0)))


def test_workflow_checkpoint_aware_datetime_json_roundtrip() -> None:
    created_at = datetime(2026, 6, 20, 12, 0, tzinfo=timezone(timedelta(hours=8)))
    checkpoint = WorkflowCheckpoint(**valid_checkpoint(createdAt=created_at))

    serialized = checkpoint.model_dump_json(by_alias=True)
    restored = WorkflowCheckpoint.model_validate_json(serialized)

    assert '"createdAt":"2026-06-20T12:00:00+08:00"' in serialized
    assert restored.created_at == created_at
    assert restored.created_at.utcoffset() == timedelta(hours=8)


def test_outline_decision_accepts_valid_outline() -> None:
    outline = OutlineDecision(**valid_outline())

    assert outline.schema_version == "1.0.0"
    assert outline.target_slide_count == len(outline.slides)
    assert outline.generated_by.skill_name == "HumanizePPT"


@pytest.mark.parametrize(
    "override",
    [
        {"targetSlideCount": 4},
        {
            "slides": [
                valid_outline()["slides"][0],
                valid_outline()["slides"][2],
                valid_outline()["slides"][1],
            ]
        },
        {"qualityScores": {"structure": 69}},
    ],
)
def test_outline_decision_rejects_invalid_quality_gates(override: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        OutlineDecision(**valid_outline(**override))


def test_visual_direction_decision_accepts_exact_three_directions() -> None:
    visual = VisualDirectionDecision(**valid_visual_direction(selectedDirectionId="apple"))

    assert visual.schema_version == "1.0.0"
    assert [direction.direction_id for direction in visual.directions] == [
        "apple",
        "mckinsey",
        "airbnb",
    ]
    assert visual.selected_direction_id == "apple"


def test_visual_direction_decision_rejects_missing_direction() -> None:
    values = valid_visual_direction()
    values["directions"] = values["directions"][:2]
    with pytest.raises(ValidationError):
        VisualDirectionDecision(**values)


def test_slide_deck_accepts_canonical_export_targets() -> None:
    deck = SlideDeck(**valid_slide_deck())

    assert deck.schema_version == "1.0.0"
    assert deck.export_targets == ["pptx", "hyperframes_html"]
    assert deck.theme.direction_id == "apple"


def test_slide_deck_rejects_split_or_unordered_export_targets() -> None:
    with pytest.raises(ValidationError):
        SlideDeck(**valid_slide_deck(exportTargets=["hyperframes_html", "pptx"]))


def valid_quality_report(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "schemaVersion": "1.0.0",
        "projectId": "project-1",
        "renderVersion": 1,
        "passed": True,
        "checks": [
            {
                "schemaVersion": "1.0.0",
                "name": "pptx_exists",
                "status": "passed",
                "detail": "PPTX exists.",
            }
        ],
    }
    values.update(overrides)
    return values


def test_render_result_requires_both_outputs_from_same_deck() -> None:
    result = RenderResult(**valid_render_result())

    assert [artifact.target for artifact in result.artifacts] == [
        "pptx",
        "hyperframes_html",
    ]
    assert {artifact.slide_count for artifact in result.artifacts} == {3}


def test_render_result_rejects_mismatched_slide_counts() -> None:
    values = valid_render_result()
    values["artifacts"][1]["slideCount"] = 4
    with pytest.raises(ValidationError):
        RenderResult(**values)


@pytest.mark.parametrize("invalid", ["", "   ", "\t\n"])
@pytest.mark.parametrize(
    ("model", "values", "field"),
    [
        (ProjectBrief, valid_brief(), "projectId"),
        (SourcePack, {"schemaVersion": "1.0.0", "projectId": "project-1"}, "projectId"),
        (WorkflowCheckpoint, valid_checkpoint(), "projectId"),
        (
            SourceItem,
            {
                "schemaVersion": "1.0.0",
                "sourceId": "source-1",
                "sourceType": "text",
                "summary": "A summary",
            },
            "sourceId",
        ),
        (
            SourceItem,
            {
                "schemaVersion": "1.0.0",
                "sourceId": "source-1",
                "sourceType": "text",
                "summary": "A summary",
            },
            "summary",
        ),
    ],
)
def test_contract_identifiers_and_summary_reject_blank_values(
    model: type[ProjectBrief | SourcePack | WorkflowCheckpoint | SourceItem],
    values: dict[str, object],
    field: str,
    invalid: str,
) -> None:
    with pytest.raises(ValidationError):
        model(**(values | {field: invalid}))


def test_quality_report_aligns_passed_with_checks() -> None:
    assert QualityReport(**valid_quality_report()).passed is True
    with pytest.raises(ValidationError):
        QualityReport(
            **valid_quality_report(
                passed=True,
                checks=[
                    {
                        "schemaVersion": "1.0.0",
                        "name": "html_frame_count",
                        "status": "failed",
                        "detail": "Mismatch.",
                    }
                ],
            )
        )


def test_schema_export_is_deterministic_and_artifacts_are_current(tmp_path: Path) -> None:
    schema_dir = ROOT / "packages" / "contracts" / "schemas"
    expected_names = {
        "outline-decision-1.0.0.json",
        "project-brief-1.0.0.json",
        "quality-report-1.0.0.json",
        "render-result-1.0.0.json",
        "slide-deck-1.0.0.json",
        "source-pack-1.0.0.json",
        "visual-direction-1.0.0.json",
        "workflow-checkpoint-1.0.0.json",
    }
    exporter = load_schema_exporter()
    rendered = exporter.render_schemas()
    exporter.write_schemas(tmp_path)
    generated = {path.name: path.read_bytes() for path in tmp_path.glob("*.json")}
    tracked = {path.name: path.read_bytes() for path in schema_dir.glob("*.json")}

    assert set(generated) == expected_names
    assert generated == rendered == tracked
    assert all(content.endswith(b"\n") for content in generated.values())
    assert b'"projectId"' in generated["project-brief-1.0.0.json"]
    assert b'"project_id"' not in generated["project-brief-1.0.0.json"]


def test_schema_drift_check_does_not_rewrite_stale_artifact(tmp_path: Path) -> None:
    exporter = load_schema_exporter()
    schema_dir = ROOT / "packages" / "contracts" / "schemas"
    copytree(schema_dir, tmp_path, dirs_exist_ok=True)
    stale_path = tmp_path / "project-brief-1.0.0.json"
    stale_path.write_bytes(b'{"stale": true}\n')
    before = stale_path.read_bytes()

    with pytest.raises(RuntimeError, match="project-brief-1.0.0.json"):
        exporter.check_schemas(tmp_path)

    assert stale_path.read_bytes() == before


def test_typescript_contracts_match_python_serialized_fields() -> None:
    typescript = (ROOT / "packages" / "contracts" / "typescript" / "index.ts").read_text(
        encoding="utf-8"
    )
    expected_interfaces = {
        "ProjectBrief": (
            ProjectBrief,
            {
                "schemaVersion: SchemaVersion;",
                "projectId: string;",
                "inputLanguage: InputLanguage;",
                "outputLanguage: OutputLanguage;",
                "deckType: DeckType;",
                "topic: string;",
                "audience: string;",
                'mode: "professional" | "one_click";',
            },
        ),
        "OutlineDecision": (
            OutlineDecision,
            {
                "schemaVersion: SchemaVersion;",
                "projectId: string;",
                "language: DeckLanguage;",
                "deckType: DeckType;",
                "audience: string;",
                "objective: string;",
                "targetSlideCount: number;",
                "narrative: string[];",
                "slides: OutlineSlide[];",
                "assetNeeds?: string[];",
                "citationNeeds?: string[];",
                "risks?: string[];",
                "qualityScores?: Record<string, number>;","generatedBy: OutlineGeneratedBy;",
            },
        ),
        "SourceItem": (
            SourceItem,
            {
                "schemaVersion: SchemaVersion;",
                "sourceId: string;",
                "sourceType: SourceType;",
                "summary: string;",
                "title?: string | null;",
                "url?: string | null;",
            },
        ),
        "SourcePack": (
            SourcePack,
            {
                "schemaVersion: SchemaVersion;",
                "projectId: string;",
                "sources?: SourceItem[];",
            },
        ),
        "WorkflowCheckpoint": (
            WorkflowCheckpoint,
            {
                "schemaVersion: SchemaVersion;",
                "projectId: string;",
                "stage: WorkflowStage;",
                "status: WorkflowStatus;",
                "version: number;",
                "payload: Record<string, unknown>;",
                "createdAt: string;",
            },
        ),
        "VisualDirectionDecision": (
            VisualDirectionDecision,
            {
                "schemaVersion: SchemaVersion;",
                "projectId: string;",
                "outlineVersion: number;",
                "directions: VisualDirection[];",
                "selectedDirectionId?: VisualDirectionId | null;",
                "generatedBy: VisualGeneratedBy;",
            },
        ),
        "SlideDeck": (
            SlideDeck,
            {
                "schemaVersion: SchemaVersion;",
                "projectId: string;",
                "outlineVersion: number;",
                "visualDirectionVersion: number;",
                "language: DeckLanguage;",
                "title: string;",
                "theme: SlideDeckTheme;",
                "slides: SlideDeckSlide[];",
                'exportTargets: ["pptx", "hyperframes_html"];',
            },
        ),
        "RenderResult": (
            RenderResult,
            {
                "schemaVersion: SchemaVersion;",
                "projectId: string;",
                "slideDeckVersion: number;",
                "artifacts: RenderArtifact[];",
            },
        ),
        "QualityReport": (
            QualityReport,
            {
                "schemaVersion: SchemaVersion;",
                "projectId: string;",
                "renderVersion: number;",
                "passed: boolean;",
                "checks: QualityCheckItem[];",
            },
        ),
    }

    for interface_name, (model, expected_lines) in expected_interfaces.items():
        interface = typescript.split(f"export interface {interface_name} {{", 1)[1].split("}", 1)[0]
        aliases = {field.alias or name for name, field in model.model_fields.items()}
        actual_lines = {line.strip() for line in interface.splitlines() if ":" in line}
        assert actual_lines == expected_lines
        assert {
            line.split(":", 1)[0].rstrip("?") for line in actual_lines
        } == aliases

    expected_types = {
        "SchemaVersion": '"1.0.0"',
        "InputLanguage": '"zh" | "en"',
        "OutputLanguage": 'InputLanguage | "bilingual"',
        "DeckType": '"course_presentation" | "thesis_defense" | "research_report" | "business_pitch" | "case_competition"',
        "SourceType": '"text" | "document" | "url" | "image"',
        "WorkflowStage": '"brief" | "outline" | "visual_direction" | "slide_deck" | "render" | "quality" | "export"',
        "WorkflowStatus": '"pending" | "draft" | "confirmed" | "failed" | "complete"',
        "DeckLanguage": 'InputLanguage | "bilingual"',
        "VisualDirectionId": '"apple" | "mckinsey" | "airbnb"',
        "RenderTarget": '"pptx" | "hyperframes_html"',
        "QualityStatus": '"passed" | "failed"',
    }
    for type_name, expected in expected_types.items():
        declaration = typescript.split(f"export type {type_name} =", 1)[1].split(";", 1)[0]
        normalized = " ".join(declaration.split()).removeprefix("| ")
        assert normalized == expected
