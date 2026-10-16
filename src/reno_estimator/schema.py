"""Data contracts.

`DraftEstimate` is what the model must return. It contains judgement only: which work items,
which quantities, which unit-price ranges and why. `Estimate` is what we return to the
user: the draft plus totals and checks computed by deterministic code.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class Chapter(StrEnum):
    DEMOLICION = "demolicion"
    ALBANILERIA = "albanileria"
    FONTANERIA = "fontaneria"
    ELECTRICIDAD = "electricidad"
    CLIMATIZACION = "climatizacion"
    CARPINTERIA_INTERIOR = "carpinteria_interior"
    CARPINTERIA_EXTERIOR = "carpinteria_exterior"
    REVESTIMIENTOS = "revestimientos"
    PAVIMENTOS = "pavimentos"
    PINTURA = "pintura"
    SANITARIOS = "sanitarios"
    MOBILIARIO_COCINA = "mobiliario_cocina"
    IMPERMEABILIZACION = "impermeabilizacion"
    RESIDUOS = "gestion_residuos"
    OTROS = "otros"


Unit = Literal["m2", "ml", "ud", "m3", "h", "pa"]
Quality = Literal["basica", "media", "alta"]


# ------------------------------------------------------------------ request


class EstimateRequest(BaseModel):
    description: str = Field(min_length=10, max_length=4000, description="What the client wants done")
    province: str | None = Field(None, description="Spanish province, affects prices")
    area_m2: float | None = Field(None, gt=0, le=2000, description="Area involved, if known")
    quality: Quality = "media"
    property_context: str | None = Field(
        None, description="Extra facts about the property, e.g. from the Catastro (year built, use)"
    )


# --------------------------------------------------------------- model output


class LineItem(BaseModel):
    chapter: Chapter
    description: str = Field(description="Concrete work item, e.g. 'Alicatado de paredes con azulejo cerámico'")
    unit: Unit
    quantity: float = Field(gt=0)
    unit_price_low: float = Field(ge=0, description="EUR per unit, excluding VAT, materials and labour")
    unit_price_high: float = Field(ge=0, description="EUR per unit, excluding VAT, materials and labour")
    confidence: float = Field(ge=0, le=1, description="How sure you are this item and quantity are needed")
    basis: str = Field(description="Why: what in the photos or description supports it, and quantity assumptions")


class DraftEstimate(BaseModel):
    summary: str = Field(description="One or two sentences describing the job")
    line_items: list[LineItem] = Field(min_length=1)
    assumptions: list[str] = Field(description="Assumptions made where information was missing")
    questions_for_client: list[str] = Field(description="Questions that would most reduce uncertainty")
    risks: list[str] = Field(description="Things that could raise the price once work starts")


# -------------------------------------------------------------- final output


class PricedLine(LineItem):
    total_low: float
    total_high: float


class Check(BaseModel):
    level: Literal["info", "warning"]
    code: str
    message: str


class Usage(BaseModel):
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_s: float = 0.0
    cost_usd: float | None = None
    attempts: int = 1


class Estimate(BaseModel):
    summary: str
    currency: Literal["EUR"] = "EUR"
    line_items: list[PricedLine]
    subtotal_low: float
    subtotal_high: float
    vat_rate: float
    total_low: float = Field(description="Including VAT")
    total_high: float = Field(description="Including VAT")
    overall_confidence: float = Field(description="Cost-weighted average of line confidences")
    assumptions: list[str]
    questions_for_client: list[str]
    risks: list[str]
    checks: list[Check]
    usage: Usage | None = None
    disclaimer: str = (
        "Estimación orientativa generada por IA. No sustituye a la visita y el presupuesto de un profesional."
    )
