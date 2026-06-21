from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence


CONTRACTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CONTRACTS_ROOT / "python"))

from ai_ppt_contracts import (  # noqa: E402
    OutlineDecision,
    ProjectBrief,
    SlideDeck,
    SourcePack,
    VisualDirectionDecision,
    WorkflowCheckpoint,
)


OUTPUT = CONTRACTS_ROOT / "schemas"
SCHEMAS = {
    "project-brief-1.0.0.json": ProjectBrief,
    "slide-deck-1.0.0.json": SlideDeck,
    "source-pack-1.0.0.json": SourcePack,
    "outline-decision-1.0.0.json": OutlineDecision,
    "workflow-checkpoint-1.0.0.json": WorkflowCheckpoint,
    "visual-direction-1.0.0.json": VisualDirectionDecision,
}


def render_schemas() -> dict[str, bytes]:
    return {
        filename: (
            json.dumps(
                model.model_json_schema(by_alias=True), indent=2, sort_keys=True
            )
            + "\n"
        ).encode("utf-8")
        for filename, model in SCHEMAS.items()
    }


def write_schemas(output: Path = OUTPUT) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for filename, rendered in render_schemas().items():
        (output / filename).write_bytes(rendered)


def check_schemas(output: Path = OUTPUT) -> None:
    rendered = render_schemas()
    drift = [
        filename
        for filename, expected in rendered.items()
        if not (output / filename).is_file()
        or (output / filename).read_bytes() != expected
    ]
    drift.extend(
        path.name for path in output.glob("*.json") if path.name not in rendered
    )
    if drift:
        raise RuntimeError(f"Schema artifacts are stale: {', '.join(sorted(drift))}")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when committed schemas differ without rewriting them.",
    )
    args = parser.parse_args(argv)
    if args.check:
        check_schemas()
    else:
        write_schemas()


if __name__ == "__main__":
    main()
