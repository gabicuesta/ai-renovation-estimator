from pathlib import Path

from reno_estimator.evals import Case, CaseResult, load_cases, score, summarise, to_markdown
from reno_estimator.pricing import price
from reno_estimator.schema import DraftEstimate, EstimateRequest, Usage

CASES = Path(__file__).parents[1] / "evals" / "cases.yaml"


def test_cases_file_is_valid():
    cases = load_cases(CASES)
    assert len(cases) >= 8
    assert all(c.reference_range[0] < c.reference_range[1] for c in cases)


def test_score(draft):
    est = price(DraftEstimate.model_validate(draft), EstimateRequest(description="Reformar el baño completo"))
    est.usage = Usage(provider="fake", model="m", input_tokens=10, output_tokens=5, latency_s=1.2)
    # subtotal is 1190–1860 €, midpoint 1525
    case = Case(
        id="c",
        description="x",
        expected_chapters=["demolicion", "fontaneria|revestimientos", "sanitarios"],
        reference_range=(1000, 2000),
    )
    r = score(case, est, "fake:m")

    assert r.recall == round(2 / 3, 3)
    assert r.hit
    assert r.overlap == round((1860 - 1190) / (2000 - 1000), 3)
    assert r.tokens == 15


def test_summary_and_report():
    results = [
        CaseResult(model="a", case_id="x", valid=True, recall=1, hit=True, overlap=0.5, spread=1.5, latency_s=2),
        CaseResult(model="a", case_id="y", valid=False, error="boom"),
    ]
    [row] = summarise(results)
    assert row["valid"] == 0.5 and row["hit_rate"] == 1.0
    md = to_markdown([row], results)
    assert "| `a` | 2 | 50%" in md and "boom" in md
