from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ProcessData(BaseModel):
    type: Literal['L', 'M', 'H'] = Field(default='L', description='AI4I Type: L/M/H')
    air_temperature_k: float = Field(ge=250, le=350)
    process_temperature_k: float = Field(ge=250, le=400)
    rotational_speed_rpm: int = Field(ge=1, le=10000)
    torque_nm: float = Field(ge=0, le=1000)
    tool_wear_min: int = Field(ge=0, le=100000)


class PredictionRequest(BaseModel):
    process_data: ProcessData


class EvidenceFeature(BaseModel):
    feature: str
    direction: Literal['high', 'low', 'normal']
    reason: str
    value: float | int | str | None = None
    tag: str | None = None


class FailureModeScore(BaseModel):
    code: str
    name: str
    probability: float
    predicted: bool


class PredictionResponse(BaseModel):
    failure_probability: float
    predicted_failure: bool
    risk_level: str
    failure_modes: list[FailureModeScore]
    predicted_modes: list[str]
    evidence_features: list[EvidenceFeature]
    recommended_actions: list[str]
    input_warnings: list[str] = []
    model_source: str
    disclaimer: str
