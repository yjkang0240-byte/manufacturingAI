from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RagSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)
    filters: dict[str, Any] | None = None


class RagChunk(BaseModel):
    chunk_id: str
    source: str
    document_title: str
    text: str
    title: str | None = None
    doc_id: str | None = None
    chunk_index: int | None = None
    doc_type: str | None = None
    equipment_type: str | None = None
    safety_gate: str | None = None
    failure_modes: str | list[str] | None = None
    related_signals: str | list[str] | None = None
    project_priority: str | None = None
    retrieval_scope: str | None = None
    section: str | None = None
    language: str | None = None
    url: str | None = None
    score: float | None = None
    distance: float | None = None
