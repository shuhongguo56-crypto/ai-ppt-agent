from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_ppt_contracts import (
    ProjectBrief,
    SourceItem,
    SourcePack,
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
        WorkflowCheckpoint(
            schemaVersion="1.0.0",
            projectId="project-1",
            stage="outline",
            status="draft",
            version=0,
            payload={},
            createdAt=datetime.now(timezone.utc),
        )


def test_schema_export_is_deterministic_and_artifacts_are_current() -> None:
    schema_dir = ROOT / "packages" / "contracts" / "schemas"
    expected_names = {
        "project-brief-1.0.0.json",
        "source-pack-1.0.0.json",
        "workflow-checkpoint-1.0.0.json",
    }
    before = {path.name: path.read_bytes() for path in schema_dir.glob("*.json")}

    command = [sys.executable, "packages/contracts/scripts/export_schemas.py"]
    subprocess.run(command, cwd=ROOT, check=True)
    first = {path.name: path.read_bytes() for path in schema_dir.glob("*.json")}
    subprocess.run(command, cwd=ROOT, check=True)
    second = {path.name: path.read_bytes() for path in schema_dir.glob("*.json")}

    assert set(first) == expected_names
    assert first == second == before
    assert all(content.endswith(b"\n") for content in first.values())
    assert b'"projectId"' in first["project-brief-1.0.0.json"]
    assert b'"project_id"' not in first["project-brief-1.0.0.json"]


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
    }
    for type_name, expected in expected_types.items():
        declaration = typescript.split(f"export type {type_name} =", 1)[1].split(";", 1)[0]
        normalized = " ".join(declaration.split()).removeprefix("| ")
        assert normalized == expected
