from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints


SchemaVersion = Literal["1.0.0"]
NonBlankString = Annotated[str, StringConstraints(min_length=1, pattern=r"\S")]


def to_camel_case(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.title() for part in rest)


class ContractModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel_case,
        populate_by_name=True,
        extra="forbid",
    )

    schema_version: SchemaVersion
