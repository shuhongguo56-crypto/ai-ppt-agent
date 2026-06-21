from __future__ import annotations

from ai_ppt_contracts import CreditPlan, CreditQuote, ProjectBrief


PLANS = [
    CreditPlan(schemaVersion="1.0.0", planId="free", name="Free", monthlyPriceUsd=0, credits=60, description="Outline and 3-page watermarked preview."),
    CreditPlan(schemaVersion="1.0.0", planId="student", name="Student", monthlyPriceUsd=7.99, credits=250, description="About 2 standard decks."),
    CreditPlan(schemaVersion="1.0.0", planId="plus", name="Plus", monthlyPriceUsd=14.99, credits=500, description="About 5 standard decks."),
    CreditPlan(schemaVersion="1.0.0", planId="pro", name="Pro", monthlyPriceUsd=29.99, credits=1000, description="About 10 standard decks."),
]


_SLIDE_COUNTS = {
    "course_presentation": 8,
    "thesis_defense": 10,
    "research_report": 8,
    "business_pitch": 8,
    "case_competition": 8,
}


def quote_project_credits(brief: ProjectBrief) -> CreditQuote:
    slides = _SLIDE_COUNTS[brief.deck_type]
    items = [
        {"schemaVersion": "1.0.0", "code": "outline", "label": "HumanizePPT outline", "credits": 10},
        {"schemaVersion": "1.0.0", "code": "visual_directions", "label": "Three visual directions", "credits": 10},
        {"schemaVersion": "1.0.0", "code": "slide_generation", "label": f"{slides} slide pages", "credits": slides * 4},
        {"schemaVersion": "1.0.0", "code": "render_quality", "label": "Local render and quality gate", "credits": 0},
    ]
    return CreditQuote(
        schemaVersion="1.0.0",
        projectId=brief.project_id,
        estimatedSlideCount=slides,
        totalCredits=sum(item["credits"] for item in items),
        items=items,
    )