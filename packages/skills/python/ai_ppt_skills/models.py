import re
from dataclasses import dataclass


_SEMANTIC_VERSION = re.compile(
    r"""
    (?:0|[1-9][0-9]*)
    \.(?:0|[1-9][0-9]*)
    \.(?:0|[1-9][0-9]*)
    (?:-
        (?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)
        (?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*
    )?
    (?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?
    \Z
    """,
    re.VERBOSE,
)
_PROMPT_HASH = re.compile(r"sha256:[0-9a-f]{64}\Z")


@dataclass(frozen=True, slots=True)
class SkillDescriptor:
    name: str
    version: str
    input_schema: str
    output_schema: str
    model: str
    prompt_hash: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("name must not be blank")
        if _SEMANTIC_VERSION.fullmatch(self.version) is None:
            raise ValueError("version must be a valid SemVer 2.0.0 version")
        if not self.input_schema.strip():
            raise ValueError("input_schema must not be blank")
        if not self.output_schema.strip():
            raise ValueError("output_schema must not be blank")
        if not self.model.strip():
            raise ValueError("model must not be blank")
        if _PROMPT_HASH.fullmatch(self.prompt_hash) is None:
            raise ValueError("prompt_hash must be sha256 followed by 64 lowercase hex digits")
