from pathlib import Path


def test_workspace_boundaries_exist() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    expected_boundaries = (
        "apps/api/app",
        "apps/web/app",
        "packages/contracts",
        "packages/skills",
        "packages/render",
        "packages/ui",
        "tests",
    )

    missing = [path for path in expected_boundaries if not (repo_root / path).is_dir()]

    assert missing == []
