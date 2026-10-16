from __future__ import annotations

import copy

import pytest

from reno_estimator.providers import ProviderResult

DRAFT = {
    "summary": "Reforma completa de baño de 5 m2 con cambio de bañera por plato de ducha.",
    "line_items": [
        {
            "chapter": "demolicion",
            "description": "Demolición de alicatado, solado y retirada de bañera",
            "unit": "m2",
            "quantity": 20,
            "unit_price_low": 15,
            "unit_price_high": 25,
            "confidence": 0.9,
            "basis": "Se cambian todos los azulejos y el suelo.",
        },
        {
            "chapter": "gestion_residuos",
            "description": "Contenedor y gestión de escombros",
            "unit": "pa",
            "quantity": 1,
            "unit_price_low": 250,
            "unit_price_high": 400,
            "confidence": 0.8,
            "basis": "Necesario tras la demolición.",
        },
        {
            "chapter": "revestimientos",
            "description": "Alicatado de paredes con azulejo cerámico",
            "unit": "m2",
            "quantity": 16,
            "unit_price_low": 40,
            "unit_price_high": 60,
            "confidence": 0.7,
            "basis": "Paredes de 2,5 m de altura, perímetro aproximado de 9 m menos huecos.",
        },
    ],
    "assumptions": ["Altura de techo de 2,5 m."],
    "questions_for_client": ["¿Se mantiene la distribución actual?"],
    "risks": ["Tuberías antiguas de plomo."],
}


@pytest.fixture
def draft() -> dict:
    return copy.deepcopy(DRAFT)


class FakeProvider:
    """Returns queued results in order and records the prompts it receives."""

    name = "fake"

    def __init__(self, *results, model: str = "fake-model"):
        self.model = model
        self._results = list(results)
        self.calls: list[dict] = []

    async def generate(self, **kwargs) -> ProviderResult:
        self.calls.append(kwargs)
        data = self._results.pop(0)
        return ProviderResult(data=data, input_tokens=1000, output_tokens=500)


@pytest.fixture
def fake_provider():
    return FakeProvider
