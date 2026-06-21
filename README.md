# AI PPT Agent — local foundation

This repository currently implements the local-first foundation from tasks 1–6: versioned shared contracts, a FastAPI service, SQLite project and checkpoint persistence, a versioned skill registry, deterministic fake text and image gateways, and strict PNG validation. The web workspace is a minimal placeholder. Outline generation and finished PowerPoint creation are not implemented yet.

The default model backend is `fake`. Local development and tests make no paid model calls and require no API key, Docker, or network access after dependencies are installed. Production database, queue, object-storage, and model-provider adapters are future work.

## Prerequisites

- Python 3.12 or newer
- Node.js 22.13 or newer
- pnpm 11.0.7 (pinned by `packageManager` in `package.json`)

## Local setup (PowerShell)

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --constraint requirements.lock -e ".[dev]"
pnpm install --frozen-lockfile
```

Keep the virtual environment activated, then run the complete offline test and type-check suite with one command:

```powershell
pnpm test
```

Runtime SQLite data and generated local assets use `.local/` by default. This directory is ignored by Git.

## Run the API

With the virtual environment activated:

```powershell
python -m uvicorn app.main:app --app-dir apps/api --reload
```

The API starts at `http://127.0.0.1:8000`. Useful routes include:

- `GET /health` — service health and version
- `POST /api/projects` — create a project from a versioned `ProjectBrief`
- `GET /api/projects/{project_id}` — read a project
- `PUT /api/projects/{project_id}/checkpoints/{stage}` — write an optimistic, versioned checkpoint
- `GET /api/projects/{project_id}/checkpoints/latest` — read the latest project checkpoint
- `GET /api/skills` — list the exact built-in skill versions and contracts

The fake text and image gateways are deterministic and intended for offline development. Image generation is pinned to `gpt-image-2`; the system must not silently fall back to another image model. Any future fallback requires an explicit product decision and user consent.
