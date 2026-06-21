# AGENTS.md

## Local Storage Defaults

- Store new Codex workspaces and intermediate files under `D:\Codex\Workspaces`.
- Store files downloaded on the user's behalf under `D:\Codex\Downloads`.
- Store user-facing generated deliverables under `D:\Codex\Outputs` unless the user requests another location.
- Do not place large generated artifacts on `C:` when a suitable `D:` location is available.
- Keep Windows application binaries and required system-managed components in their installed locations.

## Reconnection Protocol

When a new Codex session reconnects to this project, do this before changing code:

1. Read this file.
2. Read `docs/PROJECT_STATE.md`.
3. Inspect the current git state with `git status --short --branch`.
4. If continuing implementation, inspect the active worktree at `.worktrees/local-foundation` before assuming prior changes were committed.
5. Preserve user changes and unrelated work. Do not reset, checkout, delete, or overwrite files unless the user explicitly asks.

## Project North Star

This project is an international bilingual AI PPT SaaS. Users provide a topic, text, or uploaded material; the system generates a professional outline, offers high-end visual directions, then exports both editable PPTX and HyperFrames-style dynamic HTML from the same canonical `SlideDeck JSON`.

PPTX and HTML must not be generated separately. They must share one canonical deck contract first, then render into both output formats.

