from fastapi import FastAPI
from pydantic import BaseModel, Field

from faithbridge_ai.classifier import classify

app = FastAPI(title="FaithBridge AI Service", version="0.1.0")


class ClassifyRequest(BaseModel):
    text: str = Field(min_length=10, max_length=2000)


class ClassifyResponse(BaseModel):
    text: str
    category: str
    urgency_score: int
    priority: str


class MatchRequest(BaseModel):
    causes: list[str] = Field(default_factory=list)
    budget: float = Field(default=0, ge=0)


class MatchResponse(BaseModel):
    matches: list[dict]


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "faithbridge-ai"}


@app.post("/classify", response_model=ClassifyResponse)
async def classify_need(payload: ClassifyRequest) -> ClassifyResponse:
    result = classify(payload.text)
    return ClassifyResponse(text=payload.text, **result)


@app.post("/match", response_model=MatchResponse)
async def match_donors(payload: MatchRequest) -> MatchResponse:
    return MatchResponse(matches=_rank(payload.causes, payload.budget))


def _rank(causes: list[str], budget: float) -> list[dict]:
    pool = [
        {
            "program_id": "prog-1",
            "program_name": "Food Bank",
            "causes": ("food", "hunger"),
        },
        {
            "program_id": "prog-2",
            "program_name": "School Fees Fund",
            "causes": ("education", "school"),
        },
        {
            "program_id": "prog-3",
            "program_name": "Medical Assistance",
            "causes": ("medical", "health"),
        },
        {
            "program_id": "prog-4",
            "program_name": "Emergency Relief",
            "causes": ("emergency", "disaster"),
        },
        {
            "program_id": "prog-5",
            "program_name": "Employment Support",
            "causes": ("employment", "job"),
        },
    ]
    normalized = [c.lower() for c in causes]
    scored = []
    for program in pool:
        overlap = len(set(program["causes"]) & set(normalized))
        score = 0.5 if overlap else 0.1
        scored.append(
            {
                "program_id": program["program_id"],
                "program_name": program["program_name"],
                "match_score": score,
            }
        )
    scored.sort(key=lambda item: item["match_score"], reverse=True)
    return scored