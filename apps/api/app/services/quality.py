from __future__ import annotations

import re
import zipfile
from pathlib import Path

from ai_ppt_contracts import QualityReport, RenderResult


def check_render_quality(
    *,
    render_result: RenderResult,
    render_version: int,
    asset_root: Path,
) -> QualityReport:
    checks = []
    root = asset_root.resolve()
    artifacts = {artifact.target: artifact for artifact in render_result.artifacts}
    expected_slide_count = render_result.artifacts[0].slide_count

    for target in ("pptx", "hyperframes_html"):
        artifact = artifacts[target]
        path = _safe_path(root, artifact.path)
        if path is None:
            checks.append(
                {
                    "schemaVersion": "1.0.0",
                    "name": f"{target}_path",
                    "status": "failed",
                    "detail": "Artifact path is outside the asset root or missing.",
                }
            )
            continue
        checks.append(
            {
                "schemaVersion": "1.0.0",
                "name": f"{target}_exists",
                "status": "passed",
                "detail": f"{target} artifact exists and is readable.",
            }
        )

    pptx_path = _safe_path(root, artifacts["pptx"].path)
    if pptx_path is not None:
        slide_count = _pptx_slide_count(pptx_path)
        checks.append(
            {
                "schemaVersion": "1.0.0",
                "name": "pptx_slide_count",
                "status": "passed" if slide_count == expected_slide_count else "failed",
                "detail": f"PPTX contains {slide_count} slides; expected {expected_slide_count}.",
            }
        )

    html_path = _safe_path(root, artifacts["hyperframes_html"].path)
    if html_path is not None:
        frame_count = len(re.findall(r'class="frame"', html_path.read_text(encoding="utf-8")))
        checks.append(
            {
                "schemaVersion": "1.0.0",
                "name": "html_frame_count",
                "status": "passed" if frame_count == expected_slide_count else "failed",
                "detail": f"HTML contains {frame_count} frames; expected {expected_slide_count}.",
            }
        )

    return QualityReport(
        schemaVersion="1.0.0",
        projectId=render_result.project_id,
        renderVersion=render_version,
        passed=all(check["status"] == "passed" for check in checks),
        checks=checks,
    )


def _safe_path(root: Path, raw_path: str) -> Path | None:
    path = Path(raw_path)
    if not path.is_absolute():
        path = root / path
    try:
        resolved = path.resolve()
        resolved.relative_to(root)
    except (OSError, ValueError):
        return None
    return resolved if resolved.is_file() else None


def _pptx_slide_count(path: Path) -> int:
    with zipfile.ZipFile(path) as archive:
        return sum(
            1
            for name in archive.namelist()
            if name.startswith("ppt/slides/slide") and name.endswith(".xml")
        )

