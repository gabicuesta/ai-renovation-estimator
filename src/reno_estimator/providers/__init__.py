"""Provider registry: `provider:model` strings, e.g. `anthropic:claude-sonnet-5-5`."""

from __future__ import annotations

import httpx

from .anthropic import AnthropicProvider
from .base import Image, Provider, ProviderError, ProviderResult
from .gemini import GeminiProvider
from .openai import OpenAIProvider

PROVIDERS = {"anthropic": AnthropicProvider, "openai": OpenAIProvider, "gemini": GeminiProvider}

# Defaults chosen as the "balanced" tier of each vendor (October 2026). Override freely.
DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-5-5",
    "openai": "gpt-6.1-sol",
    "gemini": "gemini-3.8-flash",
}

# USD per million tokens (input, output), as published by each vendor in October 2026.
# Used only to report cost; add your models here. Unknown models report cost as None.
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "gpt-6-luna": (0.1, 0.5),
}


def parse_spec(spec: str) -> tuple[str, str]:
    provider, _, model = spec.partition(":")
    provider = provider.strip().lower()
    if provider not in PROVIDERS:
        raise ProviderError(f"Unknown provider '{provider}'. Use one of: {', '.join(PROVIDERS)}.")
    return provider, model.strip() or DEFAULT_MODELS[provider]


def get_provider(spec: str, client: httpx.AsyncClient) -> Provider:
    provider, model = parse_spec(spec)
    return PROVIDERS[provider](model, client)


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    prices = PRICES_PER_MTOK.get(model)
    if not prices:
        return None
    return round((input_tokens * prices[0] + output_tokens * prices[1]) / 1_000_000, 6)


__all__ = [
    "DEFAULT_MODELS",
    "Image",
    "Provider",
    "ProviderError",
    "ProviderResult",
    "cost_usd",
    "get_provider",
    "parse_spec",
]
