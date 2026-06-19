from __future__ import annotations

import json
import sys
from pathlib import Path


CONTRACTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CONTRACTS_ROOT / "python"))

from ai_ppt_contracts import ProjectBrief, SourcePack, WorkflowCheckpoint  # noqa: E402


OUTPUT = CONTRACTS_ROOT / "schemas"
SCHEMAS = {
    "project-brief-1.0.0.json": ProjectBrief,
    "source-pack-1.0.0.json": SourcePack,
    "workflow-checkpoint-1.0.0.json": WorkflowCheckpoint,
}


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for filename, model in SCHEMAS.items():
        rendered = json.dumps(
            model.model_json_schema(by_alias=True), indent=2, sort_keys=True
        ) + "\n"
        (OUTPUT / filename).write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
