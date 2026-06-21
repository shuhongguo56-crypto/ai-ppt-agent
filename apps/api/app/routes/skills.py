from fastapi import APIRouter

from ai_ppt_skills import builtin_registry


router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("")
def list_skills() -> dict[str, list[dict[str, str]]]:
    return {
        "skills": [
            {
                "name": item.name,
                "version": item.version,
                "inputSchema": item.input_schema,
                "outputSchema": item.output_schema,
                "model": item.model,
                "promptHash": item.prompt_hash,
            }
            for item in builtin_registry().list()
        ]
    }
