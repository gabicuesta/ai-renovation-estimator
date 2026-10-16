import pytest

from reno_estimator.pricing import price
from reno_estimator.schema import DraftEstimate, EstimateRequest

REQ = EstimateRequest(description="Reformar el baño completo", area_m2=5)


def codes(estimate):
    return {c.code for c in estimate.checks}


def test_totals_are_computed_in_code(draft):
    est = price(DraftEstimate.model_validate(draft), REQ, vat_rate=0.21)

    assert est.line_items[0].total_low == 300 and est.line_items[0].total_high == 500
    assert est.subtotal_low == 300 + 250 + 640
    assert est.subtotal_high == 500 + 400 + 960
    assert est.total_low == pytest.approx(est.subtotal_low * 1.21)
    assert est.checks == []


def test_confidence_is_cost_weighted(draft):
    draft["line_items"][2]["confidence"] = 0.1  # the most expensive line
    est = price(DraftEstimate.model_validate(draft), REQ)
    assert est.overall_confidence < 0.5
    assert "low_confidence" in codes(est)


def test_swapped_range_is_fixed(draft):
    draft["line_items"][0].update(unit_price_low=25, unit_price_high=15)
    est = price(DraftEstimate.model_validate(draft), REQ)
    assert est.line_items[0].unit_price_low == 15
    assert "swapped_range" in codes(est)


def test_unit_price_outlier(draft):
    draft["line_items"][2]["unit_price_high"] = 6000  # a whole bathroom quoted per m2
    assert "unit_price_outlier" in codes(price(DraftEstimate.model_validate(draft), REQ))


def test_quantity_inconsistent_with_area(draft):
    draft["line_items"][2]["quantity"] = 400
    assert "quantity_vs_area" in codes(price(DraftEstimate.model_validate(draft), REQ))


def test_missing_companion_chapter(draft):
    del draft["line_items"][1]  # demolition without waste management
    assert "missing_companion" in codes(price(DraftEstimate.model_validate(draft), REQ))


def test_wide_range_flagged(draft):
    draft["line_items"][2].update(unit_price_low=10, unit_price_high=90)
    assert "wide_range" in codes(price(DraftEstimate.model_validate(draft), REQ))
