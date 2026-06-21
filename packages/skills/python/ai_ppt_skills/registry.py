from .models import SkillDescriptor


class DuplicateSkill(ValueError):
    pass


class SkillRegistry:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], SkillDescriptor] = {}

    def register(self, skill: SkillDescriptor) -> None:
        key = (skill.name, skill.version)
        if key in self._items:
            raise DuplicateSkill(f"skill already registered: {skill.name}@{skill.version}")
        self._items[key] = skill

    def get(self, name: str, version: str) -> SkillDescriptor | None:
        return self._items.get((name, version))

    def list(self) -> list[SkillDescriptor]:
        return sorted(self._items.values(), key=lambda item: (item.name, item.version))


def builtin_registry() -> SkillRegistry:
    registry = SkillRegistry()
    registry.register(
        SkillDescriptor(
            name="HumanizePPT",
            version="1.0.0",
            input_schema="project-brief-1.0.0+source-pack-1.0.0",
            output_schema="outline-decision-1.0.0",
            model="gpt-5.4-mini",
            prompt_hash="sha256:9f4ea49a2e2a5204ce1eaad3c7dbeadef09674ca136a6a5e5e1e1a57fb9c1886",
        )
    )
    registry.register(
        SkillDescriptor(
            name="Frontend-Slides",
            version="1.0.0",
            input_schema="outline-decision-1.0.0",
            output_schema="visual-direction-1.0.0",
            model="gpt-5.4-mini",
            prompt_hash="sha256:0f2db8d7357e11480acfdc94ed0f3d13bfad30a6dfd58e120f1e3e14d435a0cb",
        )
    )
    return registry
