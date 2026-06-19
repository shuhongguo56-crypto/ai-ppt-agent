# AI PPT Agent Local Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build tasks 1–6 as a Docker-free local foundation with versioned contracts, a FastAPI API, durable SQLite checkpoints, a skill registry, deterministic model fakes, and strict PNG validation.

**Architecture:** The API depends on narrow repository and model-gateway protocols, with SQLite and deterministic fakes as the default adapters. Shared contracts carry explicit schema versions; all model output is validated before entering use cases, and public errors never expose prompts, uploaded text, raw provider errors, or image bytes.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, pydantic-settings, SQLite, pytest, HTTPX, TypeScript, Next.js, pnpm

---

## File map

```text
package.json                                  Root commands
pnpm-workspace.yaml                           JavaScript workspace membership
pyproject.toml                                Python package and test configuration
README.md                                     Local setup and verification
apps/web/app/page.tsx                         Minimal health placeholder
apps/web/app/layout.tsx                       Next.js root layout
apps/web/package.json                         Web scripts and dependencies
apps/web/tsconfig.json                        Strict TypeScript configuration
apps/api/app/main.py                          FastAPI application factory
apps/api/app/config.py                        Environment-backed settings
apps/api/app/errors.py                        Stable public API errors
apps/api/app/routes/projects.py               Project/checkpoint HTTP endpoints
apps/api/app/routes/skills.py                 Skill registry HTTP endpoint
apps/api/app/domain/models.py                 Project and checkpoint domain records
apps/api/app/domain/repositories.py           Repository protocols and conflicts
apps/api/app/persistence/sqlite.py             SQLite repository adapter
apps/api/app/ai/models.py                     Gateway request/response types
apps/api/app/ai/errors.py                     Safe model gateway error
apps/api/app/ai/protocols.py                  Text/image gateway protocols
apps/api/app/ai/fakes.py                      Deterministic offline gateways
apps/api/app/ai/retry.py                      Bounded retry wrapper
apps/api/app/ai/png_validator.py              Strict standalone PNG validator
apps/api/app/ai/image_result.py               Base64 decode and PNG validation boundary
packages/contracts/python/ai_ppt_contracts/   Pydantic cross-service contracts
packages/contracts/schemas/                   JSON Schema artifacts
packages/contracts/typescript/index.ts        Matching TypeScript contracts
packages/skills/python/ai_ppt_skills/         Skill descriptors and registry
apps/api/tests/                               API, persistence, registry, gateway, PNG tests
conftest.py                                   Shared isolated API test client
tests/test_contract_examples.py               Cross-package contract examples
```

### Task 1: Scaffold the local monorepo

**Files:**
- Create: `package.json`
- Create: `pnpm-workspace.yaml`
- Create: `pyproject.toml`
- Create: `apps/api/app/__init__.py`
- Create: `apps/web/package.json`
- Create: `apps/web/tsconfig.json`
- Create: `apps/web/next-env.d.ts`
- Create: `apps/web/app/layout.tsx`
- Create: `apps/web/app/page.tsx`
- Create: `apps/api/tests/test_scaffold.py`

- [ ] **Step 1: Write the failing scaffold test**

```python
# apps/api/tests/test_scaffold.py
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_workspace_boundaries_exist() -> None:
    required = [
        "apps/api/app",
        "apps/web/app",
        "packages/contracts",
        "packages/skills",
        "packages/render",
        "packages/ui",
        "tests",
    ]
    assert all((ROOT / path).exists() for path in required)
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `python -m pytest apps/api/tests/test_scaffold.py -q`

Expected: FAIL because one or more workspace boundaries do not exist.

- [ ] **Step 3: Add workspace configuration and placeholder boundaries**

```json
// package.json
{
  "name": "ai-ppt-agent",
  "private": true,
  "scripts": {
    "test:python": "python -m pytest -q",
    "test:web": "pnpm --filter @ai-ppt/web typecheck",
    "test": "pnpm test:python && pnpm test:web"
  }
}
```

```yaml
# pnpm-workspace.yaml
packages:
  - apps/web
  - packages/contracts
  - packages/ui
```

```toml
# pyproject.toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "ai-ppt-agent"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115,<1",
  "httpx>=0.28,<1",
  "pydantic>=2.10,<3",
  "pydantic-settings>=2.7,<3",
  "uvicorn>=0.34,<1"
]

[project.optional-dependencies]
dev = ["pytest>=8.3,<9"]

[tool.pytest.ini_options]
pythonpath = ["apps/api", "packages/contracts/python", "packages/skills/python"]
testpaths = ["apps/api/tests", "tests"]
addopts = "--strict-markers"

[tool.hatch.build.targets.wheel]
packages = [
  "apps/api/app",
  "packages/contracts/python/ai_ppt_contracts",
  "packages/skills/python/ai_ppt_skills"
]
```

```json
// apps/web/package.json
{
  "name": "@ai-ppt/web",
  "private": true,
  "scripts": {"dev": "next dev", "typecheck": "tsc --noEmit"},
  "dependencies": {"next": "15.3.4", "react": "19.1.0", "react-dom": "19.1.0"},
  "devDependencies": {"@types/node": "22.15.32", "@types/react": "19.1.8", "typescript": "5.8.3"}
}
```

```json
// apps/web/tsconfig.json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "esnext"],
    "strict": true,
    "noEmit": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "jsx": "preserve",
    "plugins": [{"name": "next"}]
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"]
}
```

```tsx
// apps/web/app/layout.tsx
import type { ReactNode } from "react";

export default function RootLayout({ children }: { children: ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
```

```tsx
// apps/web/app/page.tsx
export default function Home() {
  return <main><h1>AI PPT Agent</h1><p>Local foundation is ready.</p></main>;
}
```

Create zero-byte package markers at `apps/api/app/__init__.py`, `packages/render/.gitkeep`, `packages/ui/.gitkeep`, `packages/contracts/.gitkeep`, `packages/skills/.gitkeep`, and `tests/.gitkeep`. Use this exact Next.js declaration file:

```ts
/// <reference types="next" />
/// <reference types="next/image-types/global" />
// NOTE: This file is generated by Next.js and should not be edited.
```

- [ ] **Step 4: Install dependencies and rerun the scaffold test**

Run: `python -m pip install -e ".[dev]"; pnpm install; python -m pytest apps/api/tests/test_scaffold.py -q; pnpm --filter @ai-ppt/web typecheck`

Expected: Python test PASS and TypeScript exits with code 0.

- [ ] **Step 5: Commit the scaffold**

```powershell
git add package.json pnpm-workspace.yaml pnpm-lock.yaml pyproject.toml apps packages tests
git commit -m "build: scaffold local monorepo"
```

### Task 2: Define versioned cross-service contracts

**Files:**
- Create: `packages/contracts/python/ai_ppt_contracts/__init__.py`
- Create: `packages/contracts/python/ai_ppt_contracts/base.py`
- Create: `packages/contracts/python/ai_ppt_contracts/project.py`
- Create: `packages/contracts/python/ai_ppt_contracts/workflow.py`
- Create: `packages/contracts/typescript/index.ts`
- Create: `packages/contracts/schemas/project-brief-1.0.0.json`
- Create: `packages/contracts/schemas/source-pack-1.0.0.json`
- Create: `packages/contracts/schemas/workflow-checkpoint-1.0.0.json`
- Create: `packages/contracts/scripts/export_schemas.py`
- Create: `tests/test_contract_examples.py`

- [ ] **Step 1: Write contract tests first**

```python
# tests/test_contract_examples.py
import pytest
from pydantic import ValidationError

from ai_ppt_contracts import ProjectBrief, SourcePack, WorkflowCheckpoint


def test_project_brief_accepts_supported_schema() -> None:
    brief = ProjectBrief(
        schemaVersion="1.0.0",
        projectId="project-1",
        inputLanguage="zh",
        outputLanguage="en",
        deckType="course_presentation",
        topic="How CRISPR works",
        audience="Undergraduate biology students",
        mode="professional",
    )
    assert brief.schema_version == "1.0.0"


def test_contract_rejects_unknown_major_version() -> None:
    with pytest.raises(ValidationError):
        ProjectBrief(
            schemaVersion="2.0.0",
            projectId="project-1",
            inputLanguage="zh",
            outputLanguage="en",
            deckType="course_presentation",
            topic="CRISPR",
            audience="Students",
            mode="professional",
        )


def test_source_pack_and_checkpoint_require_versions() -> None:
    assert SourcePack.model_fields["schema_version"].is_required()
    assert WorkflowCheckpoint.model_fields["schema_version"].is_required()
```

- [ ] **Step 2: Run contract tests and confirm import failure**

Run: `python -m pytest tests/test_contract_examples.py -q`

Expected: FAIL with `ModuleNotFoundError: ai_ppt_contracts`.

- [ ] **Step 3: Implement the Python contracts**

```python
# packages/contracts/python/ai_ppt_contracts/base.py
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


SchemaVersion = Literal["1.0.0"]


class ContractModel(BaseModel):
    model_config = ConfigDict(alias_generator=lambda value: value.split("_")[0] + "".join(part.title() for part in value.split("_")[1:]), populate_by_name=True, extra="forbid")
    schema_version: SchemaVersion = Field(alias="schemaVersion")
```

```python
# packages/contracts/python/ai_ppt_contracts/project.py
from typing import Literal
from pydantic import Field
from .base import ContractModel


class ProjectBrief(ContractModel):
    project_id: str = Field(min_length=1)
    input_language: Literal["zh", "en"]
    output_language: Literal["zh", "en", "bilingual"]
    deck_type: Literal["course_presentation", "thesis_defense", "research_report", "business_pitch", "case_competition"]
    topic: str = Field(min_length=1, max_length=500)
    audience: str = Field(min_length=1, max_length=500)
    mode: Literal["professional", "one_click"]


class SourceItem(ContractModel):
    source_id: str
    source_type: Literal["text", "document", "url", "image"]
    summary: str
    title: str | None = None
    url: str | None = None


class SourcePack(ContractModel):
    project_id: str
    sources: list[SourceItem] = []
```

```python
# packages/contracts/python/ai_ppt_contracts/workflow.py
from datetime import datetime
from typing import Any, Literal
from pydantic import Field
from .base import ContractModel


class WorkflowCheckpoint(ContractModel):
    project_id: str
    stage: Literal["brief", "outline", "visual_direction", "slide_deck", "render", "quality", "export"]
    status: Literal["pending", "draft", "confirmed", "failed", "complete"]
    version: int = Field(ge=1)
    payload: dict[str, Any]
    created_at: datetime
```

Export the three public models from `__init__.py`.

- [ ] **Step 4: Add matching TypeScript and JSON Schema artifacts**

```ts
// packages/contracts/typescript/index.ts
export type SchemaVersion = "1.0.0";
export type Language = "zh" | "en" | "bilingual";

export interface ProjectBrief {
  schemaVersion: SchemaVersion;
  projectId: string;
  inputLanguage: "zh" | "en";
  outputLanguage: Language;
  deckType: "course_presentation" | "thesis_defense" | "research_report" | "business_pitch" | "case_competition";
  topic: string;
  audience: string;
  mode: "professional" | "one_click";
}
```

Use an exporter so artifacts are reproducible:

```python
# packages/contracts/scripts/export_schemas.py
import json
from pathlib import Path
from ai_ppt_contracts import ProjectBrief, SourcePack, WorkflowCheckpoint


OUTPUT = Path(__file__).resolve().parents[1] / "schemas"
SCHEMAS = {
    "project-brief-1.0.0.json": ProjectBrief,
    "source-pack-1.0.0.json": SourcePack,
    "workflow-checkpoint-1.0.0.json": WorkflowCheckpoint,
}


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for filename, model in SCHEMAS.items():
        rendered = json.dumps(model.model_json_schema(by_alias=True), indent=2, sort_keys=True) + "\n"
        (OUTPUT / filename).write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
```

Run: `python packages/contracts/scripts/export_schemas.py`

Expected: three deterministic JSON files appear under `packages/contracts/schemas/`.

- [ ] **Step 5: Run contract tests**

Run: `python -m pytest tests/test_contract_examples.py -q`

Expected: 3 tests PASS.

- [ ] **Step 6: Commit contracts**

```powershell
git add packages/contracts tests/test_contract_examples.py
git commit -m "feat: add versioned cross-service contracts"
```

### Task 3: Add the FastAPI shell and safe configuration

**Files:**
- Create: `apps/api/app/config.py`
- Create: `apps/api/app/errors.py`
- Create: `apps/api/app/main.py`
- Create: `apps/api/tests/conftest.py`
- Create: `apps/api/tests/test_health.py`

- [ ] **Step 1: Write health and configuration tests**

```python
# apps/api/tests/test_health.py
from app.config import Settings


def test_health_reports_service_version(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "ai-ppt-api", "version": "0.1.0"}


def test_retry_count_is_bounded() -> None:
    assert Settings(model_retry_count=1).model_retry_count == 1
```

Add parametrized invalid cases for retry counts `0` and `4`, expecting Pydantic validation errors.

- [ ] **Step 2: Run the tests and confirm import failure**

Run: `python -m pytest apps/api/tests/test_health.py -q`

Expected: FAIL because `app.config` and the `client` fixture do not exist.

- [ ] **Step 3: Implement settings, app factory, and test client**

```python
# apps/api/app/config.py
from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_PPT_", extra="ignore")
    app_name: str = "ai-ppt-api"
    app_version: str = "0.1.0"
    database_path: Path = Path(".local/ai-ppt.db")
    asset_path: Path = Path(".local/assets")
    model_backend: str = "fake"
    model_retry_count: int = Field(default=1, ge=1, le=3)


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

```python
# apps/api/app/errors.py
from dataclasses import dataclass


@dataclass(frozen=True)
class PublicError(Exception):
    code: str
    message: str
    status_code: int
```

```python
# apps/api/app/main.py
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from .config import Settings, get_settings
from .errors import PublicError


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    app = FastAPI(title=resolved.app_name, version=resolved.app_version)
    app.state.settings = resolved

    @app.exception_handler(PublicError)
    async def public_error_handler(_, exc: PublicError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message}})

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": resolved.app_name, "version": resolved.app_version}

    return app


app = create_app()
```

```python
# apps/api/tests/conftest.py
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(database_path=tmp_path / "test.db", asset_path=tmp_path / "assets"))
    with TestClient(app) as test_client:
        yield test_client
```

- [ ] **Step 4: Run API shell tests**

Run: `python -m pytest apps/api/tests/test_health.py -q`

Expected: all tests PASS.

- [ ] **Step 5: Commit the API shell**

```powershell
git add apps/api/app apps/api/tests
git commit -m "feat: add FastAPI service shell"
```

### Task 4: Persist projects and workflow checkpoints in SQLite

**Files:**
- Create: `apps/api/app/domain/models.py`
- Create: `apps/api/app/domain/repositories.py`
- Create: `apps/api/app/persistence/sqlite.py`
- Create: `apps/api/app/routes/projects.py`
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/tests/conftest.py`
- Create: `apps/api/tests/test_sqlite_repository.py`
- Create: `apps/api/tests/test_projects_api.py`

- [ ] **Step 1: Write repository tests for durability and optimistic concurrency**

```python
# apps/api/tests/test_sqlite_repository.py
from app.domain.models import ProjectRecord
from app.domain.repositories import VersionConflict
from app.persistence.sqlite import SQLiteProjectRepository


def test_project_survives_repository_reopen(tmp_path) -> None:
    path = tmp_path / "state.db"
    first = SQLiteProjectRepository(path)
    first.initialize()
    first.create(ProjectRecord.new("project-1", {"schemaVersion": "1.0.0", "topic": "CRISPR"}))
    first.close()
    second = SQLiteProjectRepository(path)
    second.initialize()
    assert second.get("project-1").project_id == "project-1"


def test_checkpoint_rejects_stale_version(tmp_path) -> None:
    repository = SQLiteProjectRepository(tmp_path / "state.db")
    repository.initialize()
    repository.create(ProjectRecord.new("project-1", {"schemaVersion": "1.0.0"}))
    repository.put_checkpoint("project-1", "brief", "draft", {"schemaVersion": "1.0.0"}, expected_version=0)
    try:
        repository.put_checkpoint("project-1", "brief", "confirmed", {"schemaVersion": "1.0.0"}, expected_version=0)
    except VersionConflict as exc:
        assert exc.current_version == 1
    else:
        raise AssertionError("stale checkpoint write must fail")
```

- [ ] **Step 2: Run repository tests and confirm failure**

Run: `python -m pytest apps/api/tests/test_sqlite_repository.py -q`

Expected: FAIL because domain and SQLite modules do not exist.

- [ ] **Step 3: Implement records, protocol, schema, and atomic writes**

```python
# apps/api/app/domain/models.py
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class ProjectRecord:
    project_id: str
    brief: dict[str, Any]
    created_at: datetime

    @classmethod
    def new(cls, project_id: str, brief: dict[str, Any]) -> "ProjectRecord":
        return cls(project_id=project_id, brief=brief, created_at=datetime.now(UTC))


@dataclass(frozen=True)
class CheckpointRecord:
    project_id: str
    stage: str
    status: str
    version: int
    payload: dict[str, Any]
    created_at: datetime
```

```python
# apps/api/app/domain/repositories.py
from dataclasses import dataclass
from typing import Protocol
from .models import CheckpointRecord, ProjectRecord


@dataclass(frozen=True)
class VersionConflict(Exception):
    current_version: int


class ProjectRepository(Protocol):
    def create(self, project: ProjectRecord) -> None: ...
    def get(self, project_id: str) -> ProjectRecord | None: ...
    def latest_checkpoint(self, project_id: str) -> CheckpointRecord | None: ...
    def put_checkpoint(self, project_id: str, stage: str, status: str, payload: dict, expected_version: int) -> CheckpointRecord: ...
```

Implement `SQLiteProjectRepository` with `sqlite3`, JSON encoded using sorted keys, `PRAGMA foreign_keys = ON`, and tables:

```sql
CREATE TABLE IF NOT EXISTS projects (
  project_id TEXT PRIMARY KEY,
  brief_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workflow_checkpoints (
  project_id TEXT NOT NULL REFERENCES projects(project_id),
  stage TEXT NOT NULL,
  status TEXT NOT NULL,
  version INTEGER NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (project_id, stage, version)
);
```

Use this repository shape; keep row conversion helpers in the same focused adapter file:

```python
# apps/api/app/persistence/sqlite.py
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from app.domain.models import CheckpointRecord, ProjectRecord
from app.domain.repositories import VersionConflict


class SQLiteProjectRepository:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")

    def initialize(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
              project_id TEXT PRIMARY KEY,
              brief_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS workflow_checkpoints (
              project_id TEXT NOT NULL REFERENCES projects(project_id),
              stage TEXT NOT NULL,
              status TEXT NOT NULL,
              version INTEGER NOT NULL,
              payload_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              PRIMARY KEY (project_id, stage, version)
            );
            """
        )

    def close(self) -> None:
        self._connection.close()

    def create(self, project: ProjectRecord) -> None:
        self._connection.execute(
            "INSERT INTO projects(project_id, brief_json, created_at) VALUES (?, ?, ?)",
            (project.project_id, json.dumps(project.brief, sort_keys=True), project.created_at.isoformat()),
        )

    def get(self, project_id: str) -> ProjectRecord | None:
        row = self._connection.execute("SELECT * FROM projects WHERE project_id = ?", (project_id,)).fetchone()
        if row is None:
            return None
        return ProjectRecord(project_id=row["project_id"], brief=json.loads(row["brief_json"]), created_at=datetime.fromisoformat(row["created_at"]))

    def latest_checkpoint(self, project_id: str) -> CheckpointRecord | None:
        row = self._connection.execute(
            "SELECT * FROM workflow_checkpoints WHERE project_id = ? ORDER BY version DESC LIMIT 1",
            (project_id,),
        ).fetchone()
        return None if row is None else self._checkpoint(row)

    def put_checkpoint(self, project_id: str, stage: str, status: str, payload: dict, expected_version: int) -> CheckpointRecord:
        now = datetime.now().astimezone()
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            row = self._connection.execute(
                "SELECT COALESCE(MAX(version), 0) AS version FROM workflow_checkpoints WHERE project_id = ? AND stage = ?",
                (project_id, stage),
            ).fetchone()
            current = int(row["version"])
            if current != expected_version:
                raise VersionConflict(current_version=current)
            version = current + 1
            self._connection.execute(
                "INSERT INTO workflow_checkpoints(project_id, stage, status, version, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (project_id, stage, status, version, json.dumps(payload, sort_keys=True), now.isoformat()),
            )
            self._connection.execute("COMMIT")
            return CheckpointRecord(project_id, stage, status, version, payload, now)
        except Exception:
            self._connection.execute("ROLLBACK")
            raise

    @staticmethod
    def _checkpoint(row: sqlite3.Row) -> CheckpointRecord:
        return CheckpointRecord(
            project_id=row["project_id"], stage=row["stage"], status=row["status"],
            version=row["version"], payload=json.loads(row["payload_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
```

- [ ] **Step 4: Run repository tests**

Run: `python -m pytest apps/api/tests/test_sqlite_repository.py -q`

Expected: repository tests PASS.

- [ ] **Step 5: Write project API tests**

```python
# apps/api/tests/test_projects_api.py
def test_create_and_read_project(client) -> None:
    payload = {
        "schemaVersion": "1.0.0",
        "projectId": "project-1",
        "inputLanguage": "zh",
        "outputLanguage": "en",
        "deckType": "course_presentation",
        "topic": "CRISPR",
        "audience": "Undergraduates",
        "mode": "professional",
    }
    created = client.post("/api/projects", json=payload)
    assert created.status_code == 201
    assert client.get("/api/projects/project-1").json()["brief"] == payload


def test_checkpoint_stale_write_returns_safe_conflict(client) -> None:
    create_project(client)
    first = client.put("/api/projects/project-1/checkpoints/brief", json={"expectedVersion": 0, "status": "draft", "payload": {"schemaVersion": "1.0.0"}})
    assert first.status_code == 200
    stale = client.put("/api/projects/project-1/checkpoints/brief", json={"expectedVersion": 0, "status": "confirmed", "payload": {"schemaVersion": "1.0.0"}})
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "checkpoint_version_conflict"
```

Add this exact helper above both tests:

```python
def create_project(client):
    return client.post("/api/projects", json={
        "schemaVersion": "1.0.0", "projectId": "project-1",
        "inputLanguage": "zh", "outputLanguage": "en",
        "deckType": "course_presentation", "topic": "CRISPR",
        "audience": "Undergraduates", "mode": "professional",
    })
```

- [ ] **Step 6: Implement and register project routes**

Use these request models and route behavior:

```python
# apps/api/app/routes/projects.py
import sqlite3
from typing import Any, Literal
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from ai_ppt_contracts import ProjectBrief
from app.domain.models import ProjectRecord
from app.domain.repositories import VersionConflict
from app.errors import PublicError


router = APIRouter(prefix="/projects", tags=["projects"])


class CheckpointWrite(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    expected_version: int = Field(alias="expectedVersion", ge=0)
    status: Literal["pending", "draft", "confirmed", "failed", "complete"]
    payload: dict[str, Any]


@router.post("", status_code=201)
def create_project(brief: ProjectBrief, request: Request) -> dict[str, Any]:
    try:
        request.app.state.repository.create(ProjectRecord.new(brief.project_id, brief.model_dump(by_alias=True, mode="json")))
    except sqlite3.IntegrityError:
        raise PublicError("project_already_exists", "Project already exists.", 409) from None
    return {"projectId": brief.project_id, "brief": brief.model_dump(by_alias=True, mode="json")}


@router.get("/{project_id}")
def get_project(project_id: str, request: Request) -> dict[str, Any]:
    project = request.app.state.repository.get(project_id)
    if project is None:
        raise PublicError("project_not_found", "Project not found.", 404)
    return {"projectId": project.project_id, "brief": project.brief, "createdAt": project.created_at.isoformat()}


@router.get("/{project_id}/checkpoints/latest")
def latest_checkpoint(project_id: str, request: Request) -> dict[str, Any]:
    checkpoint = request.app.state.repository.latest_checkpoint(project_id)
    if checkpoint is None:
        raise PublicError("checkpoint_not_found", "Checkpoint not found.", 404)
    return {"projectId": checkpoint.project_id, "stage": checkpoint.stage, "status": checkpoint.status, "version": checkpoint.version, "payload": checkpoint.payload, "createdAt": checkpoint.created_at.isoformat()}


@router.put("/{project_id}/checkpoints/{stage}")
def put_checkpoint(project_id: str, stage: str, body: CheckpointWrite, request: Request) -> dict[str, Any]:
    if request.app.state.repository.get(project_id) is None:
        raise PublicError("project_not_found", "Project not found.", 404)
    try:
        checkpoint = request.app.state.repository.put_checkpoint(project_id, stage, body.status, body.payload, body.expected_version)
    except VersionConflict:
        raise PublicError("checkpoint_version_conflict", "Checkpoint was updated by another request.", 409) from None
    return {"projectId": checkpoint.project_id, "stage": checkpoint.stage, "status": checkpoint.status, "version": checkpoint.version, "payload": checkpoint.payload, "createdAt": checkpoint.created_at.isoformat()}
```

In `create_app`, construct and initialize `SQLiteProjectRepository(resolved.database_path)`, store it on `app.state.repository`, include this router with `prefix="/api"`, and close the repository from a FastAPI lifespan context manager. Tests must create a fresh app per temporary database so connections do not leak across cases.

- [ ] **Step 7: Run persistence and API tests**

Run: `python -m pytest apps/api/tests/test_sqlite_repository.py apps/api/tests/test_projects_api.py -q`

Expected: all tests PASS.

- [ ] **Step 8: Commit persistence**

```powershell
git add apps/api/app/domain apps/api/app/persistence apps/api/app/routes apps/api/app/main.py apps/api/tests
git commit -m "feat: persist projects and workflow checkpoints"
```

### Task 5: Register HumanizePPT and Frontend-Slides skills

**Files:**
- Create: `packages/skills/python/ai_ppt_skills/__init__.py`
- Create: `packages/skills/python/ai_ppt_skills/models.py`
- Create: `packages/skills/python/ai_ppt_skills/registry.py`
- Create: `apps/api/app/routes/skills.py`
- Modify: `apps/api/app/main.py`
- Create: `apps/api/tests/test_skill_registry.py`
- Create: `apps/api/tests/test_skills_api.py`

- [ ] **Step 1: Write registry tests**

```python
# apps/api/tests/test_skill_registry.py
import pytest
from ai_ppt_skills import DuplicateSkill, SkillDescriptor, SkillRegistry, builtin_registry


def test_builtin_registry_has_two_versioned_skills() -> None:
    registry = builtin_registry()
    assert [(item.name, item.version) for item in registry.list()] == [
        ("Frontend-Slides", "1.0.0"),
        ("HumanizePPT", "1.0.0"),
    ]


def test_duplicate_name_and_version_is_rejected() -> None:
    registry = SkillRegistry()
    skill = SkillDescriptor(name="HumanizePPT", version="1.0.0", input_schema="project-brief-1.0.0", output_schema="outline-decision-1.0.0", model="gpt-5.4-mini", prompt_hash="sha256:test")
    registry.register(skill)
    with pytest.raises(DuplicateSkill):
        registry.register(skill)
```

- [ ] **Step 2: Run the test and confirm import failure**

Run: `python -m pytest apps/api/tests/test_skill_registry.py -q`

Expected: FAIL with `ModuleNotFoundError: ai_ppt_skills`.

- [ ] **Step 3: Implement immutable descriptors and registry**

```python
# packages/skills/python/ai_ppt_skills/models.py
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SkillDescriptor:
    name: str
    version: str
    input_schema: str
    output_schema: str
    model: str
    prompt_hash: str
```

```python
# packages/skills/python/ai_ppt_skills/registry.py
from .models import SkillDescriptor


class DuplicateSkill(ValueError):
    pass


class SkillRegistry:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], SkillDescriptor] = {}

    def register(self, skill: SkillDescriptor) -> None:
        key = (skill.name, skill.version)
        if key in self._items:
            raise DuplicateSkill(f"skill already registered: {skill.name}@{skill.version}")
        self._items[key] = skill

    def get(self, name: str, version: str) -> SkillDescriptor | None:
        return self._items.get((name, version))

    def list(self) -> list[SkillDescriptor]:
        return sorted(self._items.values(), key=lambda item: (item.name, item.version))
```

Add the built-ins with fixed metadata:

```python
def builtin_registry() -> SkillRegistry:
    registry = SkillRegistry()
    registry.register(SkillDescriptor(
        name="HumanizePPT", version="1.0.0",
        input_schema="project-brief-1.0.0+source-pack-1.0.0",
        output_schema="outline-decision-1.0.0", model="gpt-5.4-mini",
        prompt_hash="sha256:9f4ea49a2e2a5204ce1eaad3c7dbeadef09674ca136a6a5e5e1e1a57fb9c1886",
    ))
    registry.register(SkillDescriptor(
        name="Frontend-Slides", version="1.0.0",
        input_schema="outline-decision-1.0.0",
        output_schema="visual-direction-1.0.0", model="gpt-5.4-mini",
        prompt_hash="sha256:0f2db8d7357e11480acfdc94ed0f3d13bfad30a6dfd58e120f1e3e14d435a0cb",
    ))
    return registry
```

Export `DuplicateSkill`, `SkillDescriptor`, `SkillRegistry`, and `builtin_registry` from `ai_ppt_skills/__init__.py`.

- [ ] **Step 4: Add and test `GET /api/skills`**

```python
# apps/api/tests/test_skills_api.py
def test_list_skills(client) -> None:
    response = client.get("/api/skills")
    assert response.status_code == 200
    assert [item["name"] for item in response.json()["skills"]] == ["Frontend-Slides", "HumanizePPT"]
```

Create the route with stable camelCase output and include it from `create_app()`:

```python
# apps/api/app/routes/skills.py
from fastapi import APIRouter
from ai_ppt_skills import builtin_registry


router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("")
def list_skills() -> dict[str, list[dict[str, str]]]:
    return {"skills": [{
        "name": item.name, "version": item.version,
        "inputSchema": item.input_schema, "outputSchema": item.output_schema,
        "model": item.model, "promptHash": item.prompt_hash,
    } for item in builtin_registry().list()]}
```

Register with `app.include_router(skills.router, prefix="/api")`, then rerun both registry/API tests.

- [ ] **Step 5: Run and commit registry work**

Run: `python -m pytest apps/api/tests/test_skill_registry.py apps/api/tests/test_skills_api.py -q`

Expected: all tests PASS.

```powershell
git add packages/skills apps/api/app/routes/skills.py apps/api/app/main.py apps/api/tests
git commit -m "feat: add versioned skill registry"
```

### Task 6: Add typed model gateways, deterministic fakes, retry bounds, and safe errors

**Files:**
- Create: `apps/api/app/ai/__init__.py`
- Create: `apps/api/app/ai/models.py`
- Create: `apps/api/app/ai/errors.py`
- Create: `apps/api/app/ai/protocols.py`
- Create: `apps/api/app/ai/fakes.py`
- Create: `apps/api/app/ai/retry.py`
- Create: `apps/api/tests/test_model_gateways.py`
- Create: `apps/api/tests/test_model_safety.py`

- [ ] **Step 1: Write deterministic gateway tests**

```python
# apps/api/tests/test_model_gateways.py
import pytest
from app.ai.fakes import FakeImageGateway, FakeTextGateway
from app.ai.models import ImageRequest, TextRequest


def test_fake_text_gateway_is_deterministic() -> None:
    gateway = FakeTextGateway()
    request = TextRequest(model="gpt-5.4-mini", prompt="private prompt", response_schema={"type": "object"})
    assert gateway.generate(request) == gateway.generate(request)


def test_fake_image_gateway_is_deterministic_and_uses_image_2() -> None:
    gateway = FakeImageGateway()
    request = ImageRequest(model="gpt-image-2", prompt="private image prompt", width=2, height=2)
    first = gateway.generate(request)
    second = gateway.generate(request)
    assert first.bytes == second.bytes
    assert first.model == "gpt-image-2"


def test_image_gateway_rejects_automatic_fallback() -> None:
    with pytest.raises(ValueError, match="gpt-image-2"):
        FakeImageGateway().generate(ImageRequest(model="nano-banana-2", prompt="x", width=2, height=2))
```

- [ ] **Step 2: Run tests and confirm import failure**

Run: `python -m pytest apps/api/tests/test_model_gateways.py -q`

Expected: FAIL because `app.ai` does not exist.

- [ ] **Step 3: Implement gateway types, protocols, and fakes**

```python
# apps/api/app/ai/models.py
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class TextRequest:
    model: str
    prompt: str
    response_schema: dict[str, Any]


@dataclass(frozen=True, slots=True)
class TextResult:
    data: dict[str, Any]
    model: str
    usage: dict[str, int]


@dataclass(frozen=True, slots=True)
class ImageRequest:
    model: str
    prompt: str
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class GeneratedImage:
    bytes: bytes
    mime_type: str
    width: int
    height: int
    model: str
```

```python
# apps/api/app/ai/errors.py
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelGatewayError(Exception):
    code: str
    message: str
    retryable: bool
```

```python
# apps/api/app/ai/protocols.py
from typing import Protocol
from .models import GeneratedImage, ImageRequest, TextRequest, TextResult


class TextGateway(Protocol):
    def generate(self, request: TextRequest) -> TextResult: ...


class ImageGateway(Protocol):
    def generate(self, request: ImageRequest) -> GeneratedImage: ...
```

Use canonical JSON hashing and construct PNG bytes without Pillow:

```python
# apps/api/app/ai/fakes.py
import binascii
import hashlib
import json
import struct
import zlib
from .models import GeneratedImage, ImageRequest, TextRequest, TextResult


def _canonical_hash(payload: dict) -> bytes:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).digest()


def _chunk(kind: bytes, payload: bytes) -> bytes:
    crc = binascii.crc32(kind + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)


def _png(width: int, height: int, seed: bytes) -> bytes:
    if width < 1 or height < 1:
        raise ValueError("image dimensions must be positive")
    pixel = seed[:3]
    scanlines = b"".join(b"\x00" + pixel * width for _ in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", zlib.compress(scanlines)) + _chunk(b"IEND", b"")


class FakeTextGateway:
    def generate(self, request: TextRequest) -> TextResult:
        digest = _canonical_hash({"model": request.model, "prompt": request.prompt, "responseSchema": request.response_schema}).hex()
        return TextResult(data={"schemaVersion": "1.0.0", "fakeId": digest}, model=request.model, usage={"inputTokens": 0, "outputTokens": 0})


class FakeImageGateway:
    def generate(self, request: ImageRequest) -> GeneratedImage:
        if request.model != "gpt-image-2":
            raise ValueError("image model must be gpt-image-2; fallback requires explicit user consent")
        seed = _canonical_hash({"model": request.model, "prompt": request.prompt, "width": request.width, "height": request.height})
        return GeneratedImage(bytes=_png(request.width, request.height, seed), mime_type="image/png", width=request.width, height=request.height, model=request.model)
```

- [ ] **Step 4: Write bounded retry and sensitive-data tests**

```python
# apps/api/tests/test_model_safety.py
import logging
import pytest
from app.ai.errors import ModelGatewayError
from app.ai.retry import run_with_retry


def test_retry_stops_at_configured_limit() -> None:
    calls = 0
    def fail() -> None:
        nonlocal calls
        calls += 1
        raise ModelGatewayError("provider_unavailable", "Model provider unavailable.", True)
    with pytest.raises(ModelGatewayError):
        run_with_retry(fail, attempts=2)
    assert calls == 2


def test_retry_rejects_values_outside_one_to_three() -> None:
    with pytest.raises(ValueError):
        run_with_retry(lambda: None, attempts=4)


def test_safe_error_log_omits_sensitive_payload(caplog) -> None:
    secret = "full-private-prompt"
    with caplog.at_level(logging.WARNING):
        try:
            raise RuntimeError(secret)
        except RuntimeError:
            error = ModelGatewayError("provider_failed", "Model request failed.", False)
            logging.getLogger("ai_ppt.model").warning("model request failed", extra={"error_code": error.code})
    assert secret not in caplog.text
```

- [ ] **Step 5: Implement retry without logging exceptions or call arguments**

```python
# apps/api/app/ai/retry.py
from collections.abc import Callable
from typing import TypeVar
from .errors import ModelGatewayError


T = TypeVar("T")


def run_with_retry(operation: Callable[[], T], attempts: int) -> T:
    if attempts < 1 or attempts > 3:
        raise ValueError("attempts must be between 1 and 3")
    for index in range(attempts):
        try:
            return operation()
        except ModelGatewayError as exc:
            if not exc.retryable or index + 1 == attempts:
                raise
    raise AssertionError("retry loop exhausted without result")
```

- [ ] **Step 6: Run and commit gateway tests**

Run: `python -m pytest apps/api/tests/test_model_gateways.py apps/api/tests/test_model_safety.py -q`

Expected: all tests PASS.

```powershell
git add apps/api/app/ai apps/api/tests
git commit -m "feat: add typed deterministic model gateways"
```

### Task 7: Implement strict PNG validation and image result decoding

**Files:**
- Create: `apps/api/app/ai/png_validator.py`
- Create: `apps/api/app/ai/image_result.py`
- Create: `apps/api/tests/png_factory.py`
- Create: `apps/api/tests/test_png_validator.py`
- Create: `apps/api/tests/test_image_result.py`

- [ ] **Step 1: Add a deterministic PNG fixture factory**

```python
# apps/api/tests/png_factory.py
import binascii
import struct
import zlib


SIGNATURE = b"\x89PNG\r\n\x1a\n"


def chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF)


def png(width: int = 2, height: int = 2, color_type: int = 2, filter_byte: int = 0) -> bytes:
    channels = 3 if color_type == 2 else 4
    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    raw = b"".join(bytes([filter_byte]) + bytes(width * channels) for _ in range(height))
    return SIGNATURE + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
```

- [ ] **Step 2: Write acceptance and structure rejection tests**

```python
# apps/api/tests/test_png_validator.py
import pytest
from app.ai.png_validator import PNGValidationError, validate_png_bytes
from png_factory import SIGNATURE, chunk, png


@pytest.mark.parametrize("color_type", [2, 6])
def test_accepts_rgb_and_rgba(color_type: int) -> None:
    validate_png_bytes(png(color_type=color_type), expected_width=2, expected_height=2)


def test_rejects_bad_signature() -> None:
    with pytest.raises(PNGValidationError):
        validate_png_bytes(b"not-png", expected_width=2, expected_height=2)


def test_rejects_trailing_data() -> None:
    with pytest.raises(PNGValidationError):
        validate_png_bytes(png() + b"trailing", expected_width=2, expected_height=2)


def test_rejects_wrong_dimensions() -> None:
    with pytest.raises(PNGValidationError):
        validate_png_bytes(png(width=3), expected_width=2, expected_height=2)


def test_rejects_invalid_filter_byte() -> None:
    with pytest.raises(PNGValidationError):
        validate_png_bytes(png(filter_byte=5), expected_width=2, expected_height=2)
```

Extend the fixture module with `assemble(*chunks) -> bytes` returning `SIGNATURE + b"".join(chunks)` and `ihdr(width=2, height=2, bit_depth=8, color_type=2, compression=0, filter_method=0, interlace=0)`. Add these exact rejection cases:

```python
def assert_invalid(data: bytes, **limits) -> None:
    with pytest.raises(PNGValidationError):
        validate_png_bytes(data, expected_width=2, expected_height=2, **limits)


def test_rejects_missing_duplicate_and_misordered_required_chunks() -> None:
    header = chunk(b"IHDR", ihdr())
    pixels = chunk(b"IDAT", zlib.compress((b"\x00" + b"\x00" * 6) * 2))
    end = chunk(b"IEND", b"")
    for candidate in [
        assemble(pixels, end), assemble(header, header, pixels, end),
        assemble(header, end), assemble(header, pixels),
        assemble(header, pixels, end, end), assemble(header, end, pixels),
        assemble(header, pixels, chunk(b"IEND", b"x")),
    ]:
        assert_invalid(candidate)


def test_rejects_crc_and_size_budgets() -> None:
    corrupted = bytearray(png())
    corrupted[-1] ^= 0xFF
    assert_invalid(bytes(corrupted))
    assert_invalid(png(), max_chunk_bytes=1)
    assert_invalid(png(), max_file_bytes=len(png()) - 1)


@pytest.mark.parametrize("field,value", [
    ("bit_depth", 16), ("color_type", 0), ("compression", 1),
    ("filter_method", 1), ("interlace", 1),
])
def test_rejects_unsupported_ihdr(field: str, value: int) -> None:
    values = {"bit_depth": 8, "color_type": 2, "compression": 0, "filter_method": 0, "interlace": 0}
    values[field] = value
    data = assemble(chunk(b"IHDR", ihdr(**values)), chunk(b"IDAT", zlib.compress(b"\x00" + b"\x00" * 6) * 2), chunk(b"IEND", b""))
    assert_invalid(data)


@pytest.mark.parametrize("raw", [b"\x00" * 13, b"\x00" * 15, b"\x00" * 100])
def test_rejects_wrong_or_oversized_decompressed_payload(raw: bytes) -> None:
    data = assemble(chunk(b"IHDR", ihdr()), chunk(b"IDAT", zlib.compress(raw)), chunk(b"IEND", b""))
    assert_invalid(data)


def test_rejects_corrupt_zlib_stream() -> None:
    assert_invalid(assemble(chunk(b"IHDR", ihdr()), chunk(b"IDAT", b"not-zlib"), chunk(b"IEND", b"")))
```

- [ ] **Step 3: Run validator tests and confirm import failure**

Run: `python -m pytest apps/api/tests/test_png_validator.py -q`

Expected: FAIL because `app.ai.png_validator` does not exist.

- [ ] **Step 4: Implement the strict validator**

```python
# apps/api/app/ai/png_validator.py
import binascii
import struct
import zlib


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class PNGValidationError(ValueError):
    pass


def validate_png_bytes(data: bytes, *, expected_width: int, expected_height: int, max_chunk_bytes: int = 16 * 1024 * 1024, max_file_bytes: int = 32 * 1024 * 1024) -> None:
    if len(data) > max_file_bytes or not data.startswith(PNG_SIGNATURE):
        raise PNGValidationError("invalid PNG envelope")
    offset = len(PNG_SIGNATURE)
    chunks: list[tuple[bytes, bytes]] = []
    while offset < len(data):
        if len(data) - offset < 12:
            raise PNGValidationError("truncated chunk")
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        if length > max_chunk_bytes:
            raise PNGValidationError("chunk too large")
        end = offset + 12 + length
        if end > len(data):
            raise PNGValidationError("truncated chunk payload")
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + length]
        expected_crc = struct.unpack(">I", data[offset + 8 + length:end])[0]
        actual_crc = binascii.crc32(kind + payload) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise PNGValidationError("CRC mismatch")
        chunks.append((kind, payload))
        offset = end
        if kind == b"IEND":
            break
    if offset != len(data):
        raise PNGValidationError("data after IEND")
    _validate_chunks(chunks, expected_width, expected_height)
```

Add the complete structural/decompression helper:

```python
def _validate_chunks(chunks: list[tuple[bytes, bytes]], expected_width: int, expected_height: int) -> None:
    kinds = [kind for kind, _ in chunks]
    if not chunks or kinds[0] != b"IHDR" or kinds.count(b"IHDR") != 1:
        raise PNGValidationError("IHDR must occur exactly once and first")
    if kinds.count(b"IDAT") < 1:
        raise PNGValidationError("IDAT is required")
    if kinds.count(b"IEND") != 1 or kinds[-1] != b"IEND" or chunks[-1][1] != b"":
        raise PNGValidationError("IEND must occur exactly once and last")
    if any(index == 0 or index >= len(chunks) - 1 for index, kind in enumerate(kinds) if kind == b"IDAT"):
        raise PNGValidationError("IDAT position is invalid")

    header = chunks[0][1]
    if len(header) != 13:
        raise PNGValidationError("IHDR length must be 13")
    width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(">IIBBBBB", header)
    if width != expected_width or height != expected_height:
        raise PNGValidationError("image dimensions do not match request")
    if bit_depth != 8 or color_type not in (2, 6):
        raise PNGValidationError("unsupported pixel format")
    if compression != 0 or filter_method != 0 or interlace != 0:
        raise PNGValidationError("unsupported PNG method")

    bytes_per_pixel = 3 if color_type == 2 else 4
    expected_size = expected_height * (1 + expected_width * bytes_per_pixel)
    compressed = b"".join(payload for kind, payload in chunks if kind == b"IDAT")
    try:
        inflater = zlib.decompressobj()
        output = inflater.decompress(compressed, expected_size + 1)
        if len(output) > expected_size or inflater.unconsumed_tail:
            raise PNGValidationError("decompressed PNG exceeds budget")
        remaining = expected_size + 1 - len(output)
        if remaining > 0:
            output += inflater.flush(remaining)
    except zlib.error:
        raise PNGValidationError("invalid zlib stream") from None
    if len(output) != expected_size or not inflater.eof or inflater.unused_data:
        raise PNGValidationError("decompressed PNG length mismatch")

    row_size = 1 + expected_width * bytes_per_pixel
    if any(output[offset] > 4 for offset in range(0, expected_size, row_size)):
        raise PNGValidationError("invalid PNG filter byte")
```

Never allocate from untrusted IHDR dimensions: compare width and height to the already validated request dimensions before calculating `expected_size`.

- [ ] **Step 5: Run all PNG validator tests**

Run: `python -m pytest apps/api/tests/test_png_validator.py -q`

Expected: all valid and malicious fixture tests PASS.

- [ ] **Step 6: Write image-result boundary tests**

```python
# apps/api/tests/test_image_result.py
import base64
import pytest
from app.ai.errors import ModelGatewayError
from app.ai.image_result import decode_image_result
from app.ai.models import ImageRequest
from png_factory import png


def test_decodes_and_validates_provider_image() -> None:
    request = ImageRequest(model="gpt-image-2", prompt="private", width=2, height=2)
    result = decode_image_result(base64.b64encode(png()).decode("ascii"), request)
    assert result.mime_type == "image/png"
    assert result.width == 2


@pytest.mark.parametrize("payload", ["not-base64", base64.b64encode(b"not-png").decode("ascii")])
def test_wraps_decode_and_validation_failures(payload: str) -> None:
    request = ImageRequest(model="gpt-image-2", prompt="private", width=2, height=2)
    with pytest.raises(ModelGatewayError) as captured:
        decode_image_result(payload, request)
    assert captured.value.code == "image_validation_failed"
    assert captured.value.message == "Generated image failed validation."
    assert captured.value.retryable is False
```

- [ ] **Step 7: Implement strict base64 decode and safe wrapping**

```python
# apps/api/app/ai/image_result.py
import base64
import binascii
from .errors import ModelGatewayError
from .models import GeneratedImage, ImageRequest
from .png_validator import PNGValidationError, validate_png_bytes


def decode_image_result(encoded: str, request: ImageRequest) -> GeneratedImage:
    try:
        png_bytes = base64.b64decode(encoded, validate=True)
        validate_png_bytes(png_bytes, expected_width=request.width, expected_height=request.height)
    except (binascii.Error, PNGValidationError, ValueError):
        raise ModelGatewayError(
            code="image_validation_failed",
            message="Generated image failed validation.",
            retryable=False,
        ) from None
    return GeneratedImage(bytes=png_bytes, mime_type="image/png", width=request.width, height=request.height, model=request.model)
```

- [ ] **Step 8: Run and commit PNG work**

Run: `python -m pytest apps/api/tests/test_png_validator.py apps/api/tests/test_image_result.py -q`

Expected: all tests PASS.

```powershell
git add apps/api/app/ai apps/api/tests
git commit -m "feat: validate generated PNG assets safely"
```

### Task 8: Verify the complete offline foundation and document local use

**Files:**
- Create: `tests/test_foundation_slice.py`
- Create: `conftest.py`
- Delete: `apps/api/tests/conftest.py`
- Create: `README.md`
- Modify: `.gitignore`

- [ ] **Step 1: Write the vertical foundation test**

```python
# tests/test_foundation_slice.py
from app.ai.fakes import FakeImageGateway, FakeTextGateway
from app.ai.models import ImageRequest, TextRequest
from app.ai.png_validator import validate_png_bytes
from ai_ppt_skills import builtin_registry


def test_local_foundation_slice(client) -> None:
    health = client.get("/health")
    skills = builtin_registry().list()
    text = FakeTextGateway().generate(TextRequest(model="gpt-5.4-mini", prompt="topic", response_schema={"type": "object"}))
    image_request = ImageRequest(model="gpt-image-2", prompt="visual", width=2, height=2)
    image = FakeImageGateway().generate(image_request)
    validate_png_bytes(image.bytes, expected_width=2, expected_height=2)
    assert health.status_code == 200
    assert len(skills) == 2
    assert text.data["schemaVersion"] == "1.0.0"
```

Move the shared fixture to root `conftest.py` with this exact content, then delete `apps/api/tests/conftest.py`:

```python
# conftest.py
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(database_path=tmp_path / "test.db", asset_path=tmp_path / "assets"))
    with TestClient(app) as test_client:
        yield test_client
```

- [ ] **Step 2: Run the complete suite before documentation**

Run: `python -m pytest -q`

Expected: all tests PASS without Docker, network access, or API keys.

- [ ] **Step 3: Document exact local commands and data locations**

```markdown
# AI PPT Agent

## Local foundation

Requirements: Python 3.12 and pnpm. No Docker or API key is required.

```powershell
python -m pip install -e ".[dev]"
pnpm install
python -m pytest -q
pnpm --filter @ai-ppt/web typecheck
python -m uvicorn app.main:app --app-dir apps/api --reload
```

The API is available at `http://127.0.0.1:8000`; `GET /health` verifies startup. Local state is stored under `.local/` and must not be committed.
```

Add `.local/`, `.pytest_cache/`, `__pycache__/`, `*.pyc`, `.next/`, and `node_modules/` to `.gitignore`.

- [ ] **Step 4: Run final verification**

Run: `python -m pytest -q; pnpm --filter @ai-ppt/web typecheck; git status --short`

Expected: all tests PASS, TypeScript exits 0, and only the intended README/test/ignore changes remain.

- [ ] **Step 5: Commit final verification artifacts**

```powershell
git add README.md .gitignore tests
git commit -m "test: verify offline local foundation"
```

## Completion checklist

- [ ] `python -m pytest -q` passes offline.
- [ ] `pnpm --filter @ai-ppt/web typecheck` passes.
- [ ] `GET /health` returns the expected service/version payload.
- [ ] SQLite project and checkpoint records survive repository reopen.
- [ ] Stale checkpoint writes return a safe 409 conflict.
- [ ] Built-in skill registry exposes exactly two versioned skills.
- [ ] Text and image fakes are deterministic.
- [ ] Image model policy accepts GPT Image 2 and rejects silent fallback.
- [ ] Retry attempts are limited to 1–3.
- [ ] Public errors and ordinary logs omit sensitive payloads.
- [ ] Every required valid/malicious PNG case is covered and passes.
- [ ] No real paid model call occurs.
