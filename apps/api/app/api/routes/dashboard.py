from fastapi import APIRouter

router = APIRouter()


@router.get("/community-insights")
async def community_insights() -> dict:
    return {"totals": {"families_assisted": 0, "meals_provided": 0, "students_supported": 0}}


@router.get("/impact-report")
async def impact_report() -> dict:
    return {
        "impact_score": 0,
        "dimensions": [
            {"name": "families_supported", "score": 0},
            {"name": "education_outcomes", "score": 0},
            {"name": "employment_success", "score": 0},
            {"name": "food_security", "score": 0},
            {"name": "healthcare_support", "score": 0},
        ],
    }