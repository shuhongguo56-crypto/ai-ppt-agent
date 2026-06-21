from dataclasses import FrozenInstanceError

import pytest

from ai_ppt_skills import (
    DuplicateSkill,
    SkillDescriptor,
    SkillRegistry,
    builtin_registry,
)


HUMANIZE_HASH = (
    "sha256:9f4ea49a2e2a5204ce1eaad3c7dbeadef09674ca136a6a5e5e1e1a57fb9c1886"
)
FRONTEND_HASH = (
    "sha256:0f2db8d7357e11480acfdc94ed0f3d13bfad30a6dfd58e120f1e3e14d435a0cb"
)


def descriptor(
    *,
    name: str = "HumanizePPT",
    version: str = "1.0.0",
    input_schema: str = "project-brief-1.0.0",
    output_schema: str = "outline-decision-1.0.0",
    model: str = "gpt-5.4-mini",
    prompt_hash: str = HUMANIZE_HASH,
) -> SkillDescriptor:
    return SkillDescriptor(
        name=name,
        version=version,
        input_schema=input_schema,
        output_schema=output_schema,
        model=model,
        prompt_hash=prompt_hash,
    )


def test_builtin_registry_has_exact_versioned_skill_metadata() -> None:
    assert builtin_registry().list() == [
        SkillDescriptor(
            name="Frontend-Slides",
            version="1.0.0",
            input_schema="outline-decision-1.0.0",
            output_schema="visual-direction-1.0.0",
            model="gpt-5.4-mini",
            prompt_hash=FRONTEND_HASH,
        ),
        SkillDescriptor(
            name="HumanizePPT",
            version="1.0.0",
            input_schema="project-brief-1.0.0+source-pack-1.0.0",
            output_schema="outline-decision-1.0.0",
            model="gpt-5.4-mini",
            prompt_hash=HUMANIZE_HASH,
        ),
    ]


def test_descriptor_is_immutable_and_uses_slots() -> None:
    skill = descriptor()

    with pytest.raises(FrozenInstanceError):
        skill.name = "changed"  # type: ignore[misc]

    assert not hasattr(skill, "__dict__")


@pytest.mark.parametrize("name", ["", " ", "\t\n"])
def test_descriptor_rejects_blank_name(name: str) -> None:
    with pytest.raises(ValueError, match="name"):
        descriptor(name=name)


@pytest.mark.parametrize(
    "version",
    [
        "1.0.0-beta.1",
        "1.0.0+build.1",
        "1.0.0-beta.1+build.5",
    ],
)
def test_descriptor_accepts_semantic_version_2(version: str) -> None:
    assert descriptor(version=version).version == version


@pytest.mark.parametrize(
    "version",
    [
        "",
        "1",
        "1.0",
        "v1.0.0",
        "01.0.0",
        "1.0.0-",
        "1.0.0-beta..1",
        "1.0.0-01",
        "1.0.0 beta",
        " 1.0.0",
        "1.0.0 ",
    ],
)
def test_descriptor_rejects_invalid_version(version: str) -> None:
    with pytest.raises(ValueError, match="SemVer 2.0.0"):
        descriptor(version=version)


@pytest.mark.parametrize("field", ["input_schema", "output_schema"])
def test_descriptor_rejects_blank_schema_identifier(field: str) -> None:
    values = {field: "  "}

    with pytest.raises(ValueError, match=field):
        descriptor(**values)


@pytest.mark.parametrize("model", ["", " ", "\t\n"])
def test_descriptor_rejects_blank_model(model: str) -> None:
    with pytest.raises(ValueError, match="model"):
        descriptor(model=model)


@pytest.mark.parametrize(
    "prompt_hash",
    [
        "",
        "sha256:test",
        "sha256:" + "a" * 63,
        "sha256:" + "A" * 64,
        "md5:" + "a" * 64,
    ],
)
def test_descriptor_rejects_invalid_prompt_hash(prompt_hash: str) -> None:
    with pytest.raises(ValueError, match="prompt_hash"):
        descriptor(prompt_hash=prompt_hash)


def test_duplicate_name_and_version_is_rejected() -> None:
    registry = SkillRegistry()
    skill = descriptor()
    registry.register(skill)

    with pytest.raises(DuplicateSkill, match="HumanizePPT@1.0.0"):
        registry.register(skill)


def test_get_selects_name_and_version() -> None:
    registry = SkillRegistry()
    version_one = descriptor(version="1.0.0")
    version_two = descriptor(version="2.0.0")
    registry.register(version_two)
    registry.register(version_one)

    assert registry.get("HumanizePPT", "1.0.0") is version_one
    assert registry.get("HumanizePPT", "2.0.0") is version_two
    assert registry.get("HumanizePPT", "3.0.0") is None


def test_list_is_deterministic_and_does_not_expose_registry_storage() -> None:
    registry = SkillRegistry()
    registry.register(descriptor(name="Zulu", version="2.0.0"))
    registry.register(descriptor(name="Alpha", version="2.0.0"))
    registry.register(descriptor(name="Alpha", version="1.0.0"))

    first = registry.list()
    assert [(skill.name, skill.version) for skill in first] == [
        ("Alpha", "1.0.0"),
        ("Alpha", "2.0.0"),
        ("Zulu", "2.0.0"),
    ]

    first.clear()
    assert len(registry.list()) == 3


def test_builtin_registries_are_independent() -> None:
    first = builtin_registry()
    second = builtin_registry()
    first.register(descriptor(name="Extra"))

    assert [skill.name for skill in second.list()] == [
        "Frontend-Slides",
        "HumanizePPT",
    ]
