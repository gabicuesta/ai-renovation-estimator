"""Deterministic layer: arithmetic and sanity checks around the model's judgement.

LLMs are good at deciding *what* a job involves and bad at adding up. Here we compute every
total in code and flag anything that looks off, so a bad answer is visible instead of
looking authoritative.
"""

from __future__ import annotations

from .schema import Chapter, Check, DraftEstimate, Estimate, EstimateRequest, PricedLine

DEFAULT_VAT = 0.21

# Loose upper bounds for a unit price (EUR, excl. VAT). They catch unit mistakes,
# like quoting a whole bathroom per m2, not ordinary price differences.
MAX_UNIT_PRICE = {"m2": 1500, "ml": 1500, "m3": 2000, "h": 150, "ud": 25000, "pa": 60000}

# A job that touches these chapters almost always needs the companions too.
COMPANIONS: dict[Chapter, set[Chapter]] = {
    Chapter.DEMOLICION: {Chapter.RESIDUOS},
    Chapter.SANITARIOS: {Chapter.FONTANERIA},
    Chapter.MOBILIARIO_COCINA: {Chapter.FONTANERIA, Chapter.ELECTRICIDAD},
}

MAX_RANGE_RATIO = 3.0


def _round(x: float) -> float:
    return round(x, 2)


def price(draft: DraftEstimate, request: EstimateRequest, vat_rate: float = DEFAULT_VAT) -> Estimate:
    checks: list[Check] = []
    lines: list[PricedLine] = []

    for item in draft.line_items:
        low, high = item.unit_price_low, item.unit_price_high
        if low > high:
            low, high = high, low
            checks.append(
                Check(level="info", code="swapped_range", message=f"'{item.description}': low/high price swapped.")
            )
        if high > MAX_UNIT_PRICE[item.unit]:
            checks.append(
                Check(
                    level="warning",
                    code="unit_price_outlier",
                    message=f"'{item.description}': {high:.0f} €/{item.unit} looks too high. Check the unit.",
                )
            )
        if low > 0 and high / low > MAX_RANGE_RATIO:
            checks.append(
                Check(
                    level="info",
                    code="wide_range",
                    message=f"'{item.description}': very wide price range ({low:.0f}–{high:.0f} €).",
                )
            )
        if request.area_m2 and item.unit == "m2" and item.quantity > request.area_m2 * 4:
            # Walls can be ~3x floor area; beyond 4x the quantity is probably wrong.
            checks.append(
                Check(
                    level="warning",
                    code="quantity_vs_area",
                    message=f"'{item.description}': {item.quantity:.0f} m2 vs a declared area "
                    f"of {request.area_m2:.0f} m2.",
                )
            )
        lines.append(
            PricedLine(
                **item.model_dump(exclude={"unit_price_low", "unit_price_high"}),
                unit_price_low=low,
                unit_price_high=high,
                total_low=_round(low * item.quantity),
                total_high=_round(high * item.quantity),
            )
        )

    chapters = {line.chapter for line in lines}
    for chapter, needed in COMPANIONS.items():
        missing = needed - chapters
        if chapter in chapters and missing:
            checks.append(
                Check(
                    level="warning",
                    code="missing_companion",
                    message=f"Includes {chapter.value} but not {', '.join(sorted(m.value for m in missing))}.",
                )
            )

    subtotal_low = _round(sum(line.total_low for line in lines))
    subtotal_high = _round(sum(line.total_high for line in lines))
    weight = sum((line.total_low + line.total_high) / 2 for line in lines) or 1.0
    confidence = sum(line.confidence * (line.total_low + line.total_high) / 2 for line in lines) / weight

    if confidence < 0.5:
        checks.append(
            Check(
                level="warning",
                code="low_confidence",
                message="Low overall confidence: answer the client questions before relying on this estimate.",
            )
        )

    return Estimate(
        summary=draft.summary,
        line_items=lines,
        subtotal_low=subtotal_low,
        subtotal_high=subtotal_high,
        vat_rate=vat_rate,
        total_low=_round(subtotal_low * (1 + vat_rate)),
        total_high=_round(subtotal_high * (1 + vat_rate)),
        overall_confidence=round(confidence, 2),
        assumptions=draft.assumptions,
        questions_for_client=draft.questions_for_client,
        risks=draft.risks,
        checks=checks,
    )
