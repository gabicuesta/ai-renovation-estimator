"""Optional property context from the Catastro, via spain-open-data-mcp.

Install with `pip install "ai-renovation-estimator[catastro]"`. Year built and use change
an estimate a lot: a 1960s building often means replacing old plumbing and wiring.
"""

from __future__ import annotations


async def catastro_context(cadastral_reference: str) -> str | None:
    try:
        from spain_open_data_mcp.catastro import property_details
        from spain_open_data_mcp.http import JsonFetcher, UpstreamError, build_client
    except ImportError:
        return None

    async with build_client() as client:
        try:
            prop = await property_details(JsonFetcher(client), cadastral_reference)
        except UpstreamError:
            return None

    if prop.candidates:
        return None
    facts = [f"referencia catastral {prop.cadastral_reference}"]
    if prop.use:
        facts.append(f"uso {prop.use}")
    if prop.year_built:
        facts.append(f"construido en {prop.year_built}")
    if prop.built_area_m2:
        facts.append(f"superficie construida {prop.built_area_m2:g} m2")
    if prop.address:
        facts.append(f"dirección {prop.address}")
    return "Catastro: " + ", ".join(facts) + "."
