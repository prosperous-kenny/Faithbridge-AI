from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["food", "education", "medical", "employment", "housing", "emergency"]
Priority = Literal["critical", "high", "medium", "low"]


class AssistanceRequestIn(BaseModel):
    description: str = Field(min_length=10, max_length=2000)


class AssistanceRequestOut(BaseModel):
    id: str
    description: str
    category: Category
    urgency_score: int = Field(ge=0, le=100)
    priority: Priority
    status: str