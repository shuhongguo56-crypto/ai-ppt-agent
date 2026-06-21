# AI PPT Agent — local SaaS vertical slice

This repo now implements a local-first AI PPT SaaS workflow:

`ProjectBrief -> OutlineDecision -> confirmed outline -> 3 visual directions -> selected direction -> canonical SlideDeck JSON -> PPTX + HyperFrames HTML render -> quality check -> export/download`.

Key invariants:

- PPTX and HTML are rendered from the same `SlideDeck JSON`.
- The local backend uses deterministic fake gateways; tests make no paid model calls.
- Image generation remains pinned to `gpt-image-2`; no silent fallback is allowed.
- Export is blocked until quality checks pass.

## Local setup

```powershell
python -m pip install --constraint requirements.lock -e ".[dev]"
pnpm install --frozen-lockfile
pnpm test
```

## Run locally

API:

```powershell
python -m uvicorn app.main:app --app-dir apps/api --reload
```

Web:

```powershell
pnpm --filter @ai-ppt/web dev
```

Open:

- Landing page: `http://localhost:3000`
- Interactive workflow: `http://localhost:3000/workflow`
- API: `http://127.0.0.1:8000`

Generated assets are stored under `.local/assets` by default.