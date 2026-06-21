from typing import Literal

from pydantic import Field, model_validator

from .base import ContractModel, NonBlankString


PlanId = Literal["free", "student", "plus", "pro"]


class CreditPlan(ContractModel):
    plan_id: PlanId
    name: NonBlankString
    monthly_price_usd: float = Field(ge=0)
    credits: int = Field(ge=0)
    description: NonBlankString


class CreditQuoteItem(ContractModel):
    code: NonBlankString
    label: NonBlankString
    credits: int = Field(ge=0)


class CreditQuote(ContractModel):
    project_id: NonBlankString
    estimated_slide_count: int = Field(ge=3, le=30)
    total_credits: int = Field(ge=0)
    items: list[CreditQuoteItem] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def total_matches_items(self) -> "CreditQuote":
        if self.total_credits != sum(item.credits for item in self.items):
            raise ValueError("total_credits must equal item credits sum")
        return self