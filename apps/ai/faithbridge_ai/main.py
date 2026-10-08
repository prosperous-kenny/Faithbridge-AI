from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel, Field

from faithbridge_ai import baseline, calibration, matching


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Train or load once per process. build_model()/build_calibrator() return
    # None rather than raising when no data is available, so the service still
    # starts and degrades to the fallbacks instead of failing to boot.
    model = baseline.ensure_model_installed()
    calibrator = calibration.ensure_calibrator_installed()
    model_state = "baseline loaded" if model else "no model; using rule fallback"
    urgency_state = (
        "calibrated" if calibrator else "no calibrator; using keyword heuristic"
    )
    app.state.classifier_ready = model is not None
    print(f"[faithbridge-ai] {model_state} | urgency {urgency_state}")
    yield


app = FastAPI(title="FaithBridge AI Service", version="0.1.0", lifespan=lifespan)


class ClassifyRequest(BaseModel):
    text: str = Field(min_length=10, max_length=2000)


class ClassifyResponse(BaseModel):
    text: str
    category: str
    urgency_score: int
    priority: str
    classifier: str
    confidence: float | None = None
    # Which engine produced the urgency rating: the calibrated model or the
    # keyword heuristic fallback. Additive so old callers keep working.
    urgency_engine: str


class ProgramIn(BaseModel):
    """A program the API is offering donors. No beneficiary data ever appears
    here: matching runs on programs, and PII separation is the API's job."""

    program_id: int
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=50)
    description: str = Field(default="", max_length=2000)
    location: str | None = Field(default=None, max_length=100)
    budget_needed: int | None = Field(default=None, ge=0)
    organization_name: str = Field(default="", max_length=200)


class MatchRequest(BaseModel):
    """Donor preferences (PRD Use Case 2) plus the candidate program pool."""

    causes: list[str] = Field(default_factory=list)
    budget: float = Field(default=0, ge=0)
    location: str | None = Field(default=None, max_length=100)
    programs: list[ProgramIn] = Field(default_factory=list)


class MatchItem(BaseModel):
    program_id: int
    match_score: float
    matches_causes: bool
    matches_budget: bool
    matches_location: bool
    reason: str


class MatchResponse(BaseModel):
    engine: str
    matches: list[MatchItem]


@app.get("/health")
async def health() -> dict:
    model = baseline.installed_model()
    calibrator = calibration.installed_calibrator()
    return {
        "status": "ok",
        "service": "faithbridge-ai",
        # Reported so an operator can tell at a glance whether the Phase 0
        # baseline is actually serving, or the rule-based fallback is.
        "classifier": baseline.MODEL_ENGINE if model else baseline.FALLBACK_ENGINE,
        "urgency": (
            calibration.URGENCY_ENGINE if calibrator else calibration.FALLBACK_ENGINE
        ),
        "matching": matching.ENGINE,
    }


@app.post("/classify", response_model=ClassifyResponse)
async def classify_need(payload: ClassifyRequest) -> ClassifyResponse:
    result = baseline.classify(payload.text)
    return ClassifyResponse(text=payload.text, **result)


@app.post("/match-donors", response_model=MatchResponse)
async def match_donors(payload: MatchRequest) -> MatchResponse:
    programs = [
        matching.Program(
            program_id=program.program_id,
            name=program.name,
            category=program.category,
            description=program.description,
            location=program.location,
            budget_needed=program.budget_needed,
            organization_name=program.organization_name,
        )
        for program in payload.programs
    ]
    ranked = matching.rank_matches(
        causes=payload.causes,
        budget=payload.budget,
        location=payload.location,
        programs=programs,
    )
    return MatchResponse(
        engine=matching.ENGINE,
        matches=[
            MatchItem(
                program_id=result.program_id,
                match_score=result.match_score,
                matches_causes=result.matches_causes,
                matches_budget=result.matches_budget,
                matches_location=result.matches_location,
                reason=result.reason,
            )
            for result in ranked
        ],
    )