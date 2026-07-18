"""Pydantic models for the /evaluate request/response contract.

This contract is FROZEN — field names must not change, since the
frontend renders directly against this shape.
"""
from typing import Literal

from pydantic import BaseModel


class EvaluateRequest(BaseModel):
    product_id: str
    persona_id: str


class EvidenceItem(BaseModel):
    claim: str
    source_url: str


class FlaggedItem(BaseModel):
    item: str
    concern: str
    evidence: list[EvidenceItem]


class EvaluateResponse(BaseModel):
    verdict: Literal["eat", "moderate", "avoid"]
    headline: str
    reasoning: str
    flagged: list[FlaggedItem]
    personal_context_used: list[str]
    history_note: str
    swap: str
