from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.schemas.domain import ManufacturingContext


class EvaluationRequest(BaseModel):
    agent_answer: str
    expected_contract: dict[str, Any]
    route: list[str] | None = None
    manufacturing_context: ManufacturingContext | None = None


class EvaluationResponse(BaseModel):
    scores: dict[str, float]
    weighted_total: float
    passed: bool
    comments: list[str]
