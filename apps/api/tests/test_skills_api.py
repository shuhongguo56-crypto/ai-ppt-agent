def test_list_skills_returns_exact_stable_contract(client) -> None:
    response = client.get("/api/skills")

    assert response.status_code == 200
    assert response.json() == {
        "skills": [
            {
                "name": "Frontend-Slides",
                "version": "1.0.0",
                "inputSchema": "outline-decision-1.0.0",
                "outputSchema": "visual-direction-1.0.0",
                "model": "gpt-5.4-mini",
                "promptHash": "sha256:0f2db8d7357e11480acfdc94ed0f3d13bfad30a6dfd58e120f1e3e14d435a0cb",
            },
            {
                "name": "HumanizePPT",
                "version": "1.0.0",
                "inputSchema": "project-brief-1.0.0+source-pack-1.0.0",
                "outputSchema": "outline-decision-1.0.0",
                "model": "gpt-5.4-mini",
                "promptHash": "sha256:9f4ea49a2e2a5204ce1eaad3c7dbeadef09674ca136a6a5e5e1e1a57fb9c1886",
            },
        ]
    }
