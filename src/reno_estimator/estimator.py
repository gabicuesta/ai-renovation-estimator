"""Orchestration: prompt → model → validate (with one repair attempt) → deterministic pricing."""

from __future__ import annotations

import copy
import json
import time
from typing import Any

from pydantic import ValidationError

from .pricing import DEFAULT_VAT, price
from .providers import Image, Provider, ProviderError, cost_usd
from .schema import Chapter, DraftEstimate, Estimate, EstimateRequest, Usage

SCHEMA_NAME = "submit_estimate"

SYSTEM_PROMPT = f"""\
Eres un jefe de obra con 20 años de experiencia en reformas de viviendas en España.
Preparas estimaciones previas a la visita a partir de fotos y de la descripción del cliente.

Reglas:
- Desglosa el trabajo en partidas concretas, como en un presupuesto real. Usa estos capítulos:
  {", ".join(c.value for c in Chapter)}.
- Para cada partida da cantidad y unidad (m2, ml, ud, m3, h, pa) y un rango de precio unitario
  en euros SIN IVA (material y mano de obra) para la provincia indicada y precios actuales.
- No calcules totales: los calcula el sistema a partir de cantidades y precios unitarios.
- Si falta información, haz supuestos razonables y explícitos en `assumptions`, baja la
  `confidence` de esa partida y añade la pregunta que lo resolvería en `questions_for_client`.
- Incluye siempre lo que un profesional no olvidaría: demolición y retirada de escombros,
  protecciones, ayudas de albañilería, remates.
- No inventes lo que no se ve ni se describe. Si algo es dudoso, ponlo en `risks`.
- Escribe en español.
"""


def _inline_refs(schema: dict) -> dict:
    """Resolve `$ref`s into a self-contained schema: the most portable form across vendors."""
    schema = copy.deepcopy(schema)
    defs = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return resolve(defs[node["$ref"].split("/")[-1]])
            return {k: resolve(v) for k, v in node.items()}
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node

    return resolve(schema)


DRAFT_SCHEMA = _inline_refs(DraftEstimate.model_json_schema())


def build_prompt(request: EstimateRequest, n_images: int) -> str:
    lines = [f"Descripción del cliente: {request.description}"]
    lines.append(f"Provincia: {request.province or 'no indicada (usa precios medios de España)'}")
    if request.area_m2:
        lines.append(f"Superficie aproximada indicada: {request.area_m2:g} m2")
    lines.append(f"Calidad de acabados deseada: {request.quality}")
    if request.property_context:
        lines.append(f"Datos del inmueble: {request.property_context}")
    lines.append(f"Fotos adjuntas: {n_images}" if n_images else "No hay fotos: básate solo en la descripción.")
    lines.append(f"Devuelve la estimación con el esquema `{SCHEMA_NAME}`.")
    return "\n".join(lines)


class EstimationError(RuntimeError):
    pass


async def estimate(
    request: EstimateRequest,
    provider: Provider,
    images: list[Image] | None = None,
    vat_rate: float = DEFAULT_VAT,
    max_attempts: int = 2,
) -> Estimate:
    images = images or []
    prompt = build_prompt(request, len(images))
    usage = Usage(provider=provider.name, model=provider.model, attempts=0)
    started = time.perf_counter()
    last_error = ""

    for _ in range(max_attempts):
        usage.attempts += 1
        attempt_prompt = prompt
        if last_error:
            attempt_prompt += (
                "\n\nTu respuesta anterior no cumplía el esquema. Corrige estos errores y responde de nuevo:\n"
                + last_error
            )
        try:
            result = await provider.generate(
                system=SYSTEM_PROMPT, prompt=attempt_prompt, images=images, schema=DRAFT_SCHEMA, schema_name=SCHEMA_NAME
            )
        except ProviderError as exc:
            raise EstimationError(str(exc)) from exc

        usage.input_tokens += result.input_tokens
        usage.output_tokens += result.output_tokens
        try:
            data = result.data if isinstance(result.data, dict) else json.loads(str(result.data))
            draft = DraftEstimate.model_validate(data)
        except (ValidationError, json.JSONDecodeError) as exc:
            last_error = str(exc)[:1500]
            continue

        final = price(draft, request, vat_rate)
        usage.latency_s = round(time.perf_counter() - started, 2)
        usage.cost_usd = cost_usd(provider.model, usage.input_tokens, usage.output_tokens)
        final.usage = usage
        return final

    raise EstimationError(f"The model did not return a valid estimate after {max_attempts} attempts: {last_error}")
