from typing import Literal

from pydantic import Field, model_validator

from .base import ContractModel, NonBlankString


QualityStatus = Literal["passed", "failed"]


class QualityCheckItem(ContractModel):
    name: NonBlankString
    status: QualityStatus
    detail: NonBlankString


class QualityReport(ContractModel):
    project_id: NonBlankString
    render_version: int = Field(ge=1)
    passed: bool
    checks: list[QualityCheckItem] = Field(min_length=1, max_length=48)

    @model_validator(mode="after")
    def align_passed_with_checks(self) -> "QualityReport":
        all_passed = all(check.status == "passed" for check in self.checks)
        if self.passed != all_passed:
            raise ValueError("passed must match all check statuses")
        return self
