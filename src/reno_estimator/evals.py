"""Evals: run the same cases against several models and compare quality, cost and latency.

    reno-evals --models anthropic: openai: gemini: --repeats 2

Metrics per case
  valid          the model returned a schema-valid estimate (after at most one repair)
  recall         share of expected chapters present
  hit            the midpoint of the estimate falls inside the reference range
  overlap        IoU between the estimated and the reference range (0..1)
  spread         high / low of the estimate: how decisive the model is
  warnings       deterministic checks raised (lower is better)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import httpx
import yaml

from .env import load_dotenv
from .estimator import EstimationError, estimate
from .images import prepare
from .providers import get_provider, parse_spec
from .schema import Estimate, EstimateRequest


@dataclass
class Case:
    id: str
    description: str
    expected_chapters: list[str]
    reference_range: tuple[float, float]
    province: str | None = None
    area_m2: float | None = None
    quality: str = "media"
    photos: list[str] = field(default_factory=list)
    photo_bytes: list[bytes] = field(default_factory=list, repr=False)


@dataclass
class CaseResult:
    model: str
    case_id: str
    valid: bool
    recall: float = 0.0
    hit: bool = False
    overlap: float = 0.0
    spread: float | None = None
    warnings: int = 0
    latency_s: float | None = None
    tokens: int = 0
    cost_usd: float | None = None
    error: str | None = None


def load_cases(path: Path) -> list[Case]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    cases = []
    for c in raw["cases"]:
        c["reference_range"] = tuple(c["reference_range"])
        c["photos"] = [str((path.parent / p).resolve()) for p in c.get("photos", [])]
        c["photo_bytes"] = [Path(p).read_bytes() for p in c["photos"]]
        cases.append(Case(**c))
    return cases


def score(case: Case, est: Estimate, model: str) -> CaseResult:
    present = {line.chapter.value for line in est.line_items}
    hits = sum(1 for alt in case.expected_chapters if set(alt.split("|")) & present)
    recall = hits / len(case.expected_chapters) if case.expected_chapters else 1.0

    lo, hi = est.subtotal_low, est.subtotal_high
    ref_lo, ref_hi = case.reference_range
    mid = (lo + hi) / 2
    inter = max(0.0, min(hi, ref_hi) - max(lo, ref_lo))
    union = max(hi, ref_hi) - min(lo, ref_lo)

    u = est.usage
    return CaseResult(
        model=model,
        case_id=case.id,
        valid=True,
        recall=round(recall, 3),
        hit=ref_lo <= mid <= ref_hi,
        overlap=round(inter / union, 3) if union > 0 else 0.0,
        spread=round(hi / lo, 2) if lo > 0 else None,
        warnings=sum(1 for c in est.checks if c.level == "warning"),
        latency_s=u.latency_s if u else None,
        tokens=(u.input_tokens + u.output_tokens) if u else 0,
        cost_usd=u.cost_usd if u else None,
    )


def summarise(results: list[CaseResult]) -> list[dict]:
    rows = []
    for model in dict.fromkeys(r.model for r in results):
        rs = [r for r in results if r.model == model]
        ok = [r for r in rs if r.valid]
        costs = [r.cost_usd for r in ok if r.cost_usd is not None]
        rows.append(
            {
                "model": model,
                "runs": len(rs),
                "valid": len(ok) / len(rs),
                "recall": statistics.mean(r.recall for r in ok) if ok else 0.0,
                "hit_rate": statistics.mean(1.0 if r.hit else 0.0 for r in ok) if ok else 0.0,
                "overlap": statistics.mean(r.overlap for r in ok) if ok else 0.0,
                "spread": statistics.median(r.spread for r in ok if r.spread) if ok else None,
                "warnings": statistics.mean(r.warnings for r in ok) if ok else None,
                "p50_latency_s": statistics.median(r.latency_s for r in ok if r.latency_s is not None) if ok else None,
                "cost_usd": round(sum(costs), 4) if costs else None,
            }
        )
    return rows


def to_markdown(summary: list[dict], results: list[CaseResult]) -> str:
    def fmt(v, pct=False, digits=2):
        if v is None:
            return "–"
        return f"{v:.0%}" if pct else f"{v:.{digits}f}"

    out = [
        f"# Eval results · {datetime.now():%Y-%m-%d %H:%M}",
        "",
        "| Model | Runs | Valid | Chapter recall | Hit rate | Range IoU | Spread (hi/lo) | Warnings/run "
        "| p50 latency | Cost |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in summary:
        out.append(
            f"| `{s['model']}` | {s['runs']} | {fmt(s['valid'], True)} | {fmt(s['recall'], True)} "
            f"| {fmt(s['hit_rate'], True)} | {fmt(s['overlap'])} | {fmt(s['spread'])} | {fmt(s['warnings'], digits=1)} "
            f"| {fmt(s['p50_latency_s'], digits=1)} s "
            f"| {'$' + fmt(s['cost_usd'], digits=4) if s['cost_usd'] else '–'} |"
        )
    out += [
        "",
        "## Per case",
        "",
        "| Model | Case | Valid | Recall | Hit | IoU | Warnings | Error |",
        "|---|---|---|---:|---|---:|---:|---|",
    ]
    for r in results:
        out.append(
            f"| `{r.model}` | {r.case_id} | {'✓' if r.valid else '✗'} | {fmt(r.recall, True)} "
            f"| {'✓' if r.hit else '✗'} | {fmt(r.overlap)} | {r.warnings} | {r.error or ''} |"
        )
    return "\n".join(out) + "\n"


async def run(cases: list[Case], specs: list[str], repeats: int = 1, concurrency: int = 4) -> list[CaseResult]:
    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=10.0)) as client:

        async def one(spec: str, case: Case) -> CaseResult:
            provider = get_provider(spec, client)
            label = f"{provider.name}:{provider.model}"
            request = EstimateRequest(
                description=case.description, province=case.province, area_m2=case.area_m2, quality=case.quality
            )
            images = prepare(case.photo_bytes)
            async with sem:
                try:
                    est = await estimate(request, provider, images)
                except EstimationError as exc:
                    return CaseResult(model=label, case_id=case.id, valid=False, error=str(exc)[:120])
            return score(case, est, label)

        jobs = [one(spec, case) for spec in specs for case in cases for _ in range(repeats)]
        return list(await asyncio.gather(*jobs))


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare models on the renovation eval set")
    parser.add_argument("--cases", default="evals/cases.yaml")
    parser.add_argument("--models", nargs="+", default=["anthropic:", "openai:", "gemini:"])
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--out", default="evals/results")
    args = parser.parse_args()
    load_dotenv()

    for spec in args.models:
        parse_spec(spec)  # fail fast on typos
    cases = load_cases(Path(args.cases))
    results = asyncio.run(run(cases, args.models, args.repeats))
    summary = summarise(results)
    report = to_markdown(summary, results)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    (out / f"{stamp}.md").write_text(report, encoding="utf-8")
    (out / f"{stamp}.json").write_text(
        json.dumps({"summary": summary, "results": [asdict(r) for r in results]}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(report)


if __name__ == "__main__":
    main()
