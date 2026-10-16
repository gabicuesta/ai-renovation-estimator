"""Command line: `reno-estimate "Reformar baño de 5 m2" --photo bano.jpg --model openai:`"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

import httpx

from .context import catastro_context
from .env import load_dotenv
from .estimator import EstimationError, estimate
from .images import ImageError, prepare
from .providers import DEFAULT_MODELS, ProviderError, get_provider
from .schema import EstimateRequest


def _eur(n: float) -> str:
    return f"{n:,.0f} €".replace(",", ".")


async def _run(args: argparse.Namespace, photos: list[bytes]) -> int:
    context = await catastro_context(args.catastro) if args.catastro else None
    request = EstimateRequest(
        description=args.description,
        province=args.province,
        area_m2=args.area,
        quality=args.quality,
        property_context=context,
    )
    images = prepare(photos)
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
        result = await estimate(request, get_provider(args.model, client), images)

    if args.json:
        print(result.model_dump_json(indent=2))
        return 0

    print(f"\n{result.summary}\n")
    for line in result.line_items:
        print(
            f"  [{line.chapter.value:<20}] {line.description[:60]:<60} "
            f"{line.quantity:>7g} {line.unit:<3} {_eur(line.total_low):>10} – {_eur(line.total_high):>10}"
        )
    print(f"\n  Total (IVA {result.vat_rate:.0%} incl.): {_eur(result.total_low)} – {_eur(result.total_high)}")
    print(f"  Confianza: {result.overall_confidence:.0%}")
    for check in result.checks:
        print(f"  ! {check.message}")
    if result.questions_for_client:
        print("\n  Preguntas para el cliente:")
        for q in result.questions_for_client:
            print(f"   - {q}")
    u = result.usage
    if u:
        cost = f" · ${u.cost_usd:.4f}" if u.cost_usd is not None else ""
        print(f"\n  {u.provider}:{u.model} · {u.latency_s}s · {u.input_tokens + u.output_tokens} tokens{cost}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="AI renovation estimator")
    parser.add_argument("description")
    parser.add_argument("--photo", action="append", default=[], help="Photo path (repeatable)")
    parser.add_argument("--province")
    parser.add_argument("--area", type=float, help="Area in m2")
    parser.add_argument("--quality", choices=["basica", "media", "alta"], default="media")
    parser.add_argument("--catastro", help="Cadastral reference to enrich the context")
    parser.add_argument(
        "--model",
        default=os.environ.get("RENO_MODEL", f"anthropic:{DEFAULT_MODELS['anthropic']}"),
        help="provider:model, e.g. anthropic:claude-sonnet-5-5, openai:gpt-6.1-sol, gemini:gemini-3.8-flash",
    )
    parser.add_argument("--json", action="store_true", help="Print the full JSON result")
    args = parser.parse_args()
    load_dotenv()
    try:
        photos = [Path(p).read_bytes() for p in args.photo]
        sys.exit(asyncio.run(_run(args, photos)))
    except (EstimationError, ProviderError, ImageError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
