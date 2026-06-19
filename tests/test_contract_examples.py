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
    expected_fields = {
        "ProjectBrief": ProjectBrief,
        "SourceItem": SourceItem,
        "SourcePack": SourcePack,
        "WorkflowCheckpoint": WorkflowCheckpoint,
    }

    for interface_name, model in expected_fields.items():
        interface = typescript.split(f"export interface {interface_name} {{", 1)[1].split("}", 1)[0]
        aliases = {field.alias or name for name, field in model.model_fields.items()}
        assert {line.strip().split(":", 1)[0].rstrip("?") for line in interface.splitlines() if ":" in line} == aliases

    assert 'export type SchemaVersion = "1.0.0";' in typescript
