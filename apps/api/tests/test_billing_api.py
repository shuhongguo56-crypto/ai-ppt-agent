PROJECT = {
    "schemaVersion": "1.0.0",
    "projectId": "project-billing",
    "inputLanguage": "zh",
    "outputLanguage": "en",
    "deckType": "course_presentation",
    "topic": "CRISPR",
    "audience": "Undergraduates",
    "mode": "professional",
}


def test_billing_plans_are_public_and_stable(client) -> None:
    response = client.get("/api/billing/plans")

    assert response.status_code == 200
    plans = response.json()["plans"]
    assert [plan["planId"] for plan in plans] == ["free", "student", "plus", "pro"]
    assert plans[0]["credits"] == 60
    assert plans[-1]["monthlyPriceUsd"] == 29.99


def test_project_credit_quote_uses_brief_and_itemizes_cost(client) -> None:
    assert client.post("/api/projects", json=PROJECT).status_code == 201

    response = client.get("/api/projects/project-billing/credits/quote")

    assert response.status_code == 200
    quote = response.json()["quote"]
    assert quote["projectId"] == "project-billing"
    assert quote["estimatedSlideCount"] == 8
    assert quote["totalCredits"] == sum(item["credits"] for item in quote["items"])
    assert {item["code"] for item in quote["items"]} == {
        "outline",
        "visual_directions",
        "slide_generation",
        "render_quality",
    }


def test_project_credit_quote_missing_project_is_safe(client) -> None:
    response = client.get("/api/projects/missing/credits/quote")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "project_not_found"