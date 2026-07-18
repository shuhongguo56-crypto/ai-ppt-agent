from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.ai.image_dimensions import read_raster_dimensions


@dataclass(frozen=True, slots=True)
class ImageResolutionRequirement:
    min_long_edge: int
    min_short_edge: int
    label: str


EXPERT_PAGE_RESOLUTION = ImageResolutionRequirement(1920, 1080, "2K expert page")
EXPERT_KEY_PAGE_RESOLUTION = ImageResolutionRequirement(3840, 2160, "4K key page")


def raster_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        return read_raster_dimensions(path.read_bytes())
    except OSError:
        return None


def meets_resolution(
    dimensions: tuple[int, int] | None,
    requirement: ImageResolutionRequirement,
) -> bool:
    if dimensions is None:
        return False
    width, height = dimensions
    long_edge, short_edge = max(width, height), min(width, height)
    return long_edge >= requirement.min_long_edge and short_edge >= requirement.min_short_edge


def upscale_with_realesrgan(
    source: Path,
    destination: Path,
    *,
    executable: Path | None,
    requirement: ImageResolutionRequirement,
    model: str = "realesrgan-x4plus",
    timeout_seconds: float = 180,
) -> tuple[int, int] | None:
    """Upscale a raster visual with the official Real-ESRGAN ncnn executable."""

    if executable is None or not executable.is_file() or not source.is_file():
        return None
    current = raster_dimensions(source)
    if current is None:
        return None
    if meets_resolution(current, requirement):
        if source.resolve() != destination.resolve():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        return current
    width, height = current
    required_scale = max(
        requirement.min_long_edge / max(width, height),
        requirement.min_short_edge / min(width, height),
    )
    scale = 2 if required_scale <= 2 else 3 if required_scale <= 3 else 4
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)
    command = [
        str(executable),
        "-i",
        str(source),
        "-o",
        str(destination),
        "-n",
        model,
        "-s",
        str(scale),
        "-f",
        "png",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=executable.parent,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        destination.unlink(missing_ok=True)
        return None
    if completed.returncode != 0 or not destination.is_file():
        destination.unlink(missing_ok=True)
        return None
    dimensions = raster_dimensions(destination)
    if not meets_resolution(dimensions, requirement):
        destination.unlink(missing_ok=True)
        return None
    return dimensions
