from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VisualPlacement:
    mode: str
    gravity: str
    x: int
    y: int
    cx: int
    cy: int
    rounded: bool = True
    reading_zone: tuple[int, int, int, int] | None = None


# Original, content-driven composition primitives. The library borrows only
# general layout principles from MIT/Apache-licensed presentation tools; it
# contains no copied third-party templates or artwork.
COMPOSITION_LIBRARY: dict[str, VisualPlacement] = {
    "cinematic_hero": VisualPlacement("window", "right-hero", 7280000, 650000, 4250000, 5100000),
    "editorial_cover": VisualPlacement("window", "left-editorial", 620000, 700000, 4860000, 5100000),
    "architectural_cover": VisualPlacement("window", "upper-panorama", 4240000, 700000, 7200000, 2200000),
    "chapter_index": VisualPlacement("full_bleed", "full-bleed-right-focus", 0, 0, 12192000, 6858000, False, (0, 0, 7040000, 6858000)),
    "editorial_split": VisualPlacement("edge_panel", "left-edge", 0, 0, 5380000, 6858000, False),
    "diagonal_story": VisualPlacement("full_bleed", "diagonal-depth", 0, 0, 12192000, 6858000, False, (0, 0, 6600000, 6858000)),
    "statement_focus": VisualPlacement("full_bleed", "center-stage", 0, 0, 12192000, 6858000, False, (1180000, 900000, 9840000, 5050000)),
    "proof_mosaic": VisualPlacement("window", "upper-right-mosaic", 7060000, 920000, 4300000, 2840000),
    "data_landscape": VisualPlacement("window", "upper-right-evidence", 8040000, 560000, 3300000, 1120000),
    "process_ribbon": VisualPlacement("strip", "upper-cinematic-strip", 650000, 1780000, 10900000, 720000),
    "system_map": VisualPlacement("window", "center-anchor", 4380000, 1840000, 3440000, 3140000),
    "split_comparison": VisualPlacement("window", "center-medallion", 5530000, 2620000, 1120000, 1700000),
    "priority_stack": VisualPlacement("edge_panel", "right-edge", 9540000, 720000, 1980000, 5400000),
    "manifesto_close": VisualPlacement("full_bleed", "full-bleed-left-focus", 0, 0, 12192000, 6858000, False, (1250000, 900000, 9700000, 4800000)),
    "future_horizon": VisualPlacement("full_bleed", "horizon", 0, 0, 12192000, 6858000, False, (1250000, 900000, 9700000, 4800000)),
    "closing_echo": VisualPlacement("full_bleed", "quiet-center", 0, 0, 12192000, 6858000, False, (1250000, 900000, 9700000, 4800000)),
}


def visual_placement(archetype: str) -> VisualPlacement:
    return COMPOSITION_LIBRARY.get(archetype, COMPOSITION_LIBRARY["cinematic_hero"])
