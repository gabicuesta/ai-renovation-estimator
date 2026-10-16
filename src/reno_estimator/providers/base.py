"""Provider-agnostic contract.

Each provider is a thin HTTP adapter (no vendor SDKs): it turns a system prompt, a user
prompt, images and a JSON Schema into one request, and returns the JSON the model
produced plus token usage. Validation and retries live in the estimator, not here, so
every provider is held to exactly the same bar.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx


@dataclass(frozen=True)
class Image:
    media_type: str  # image/jpeg, image/png, image/webp
    data_b64: str


@dataclass
class ProviderResult:
    data: Any  # parsed JSON, or the raw text if it could not be parsed
    input_tokens: int = 0
    output_tokens: int = 0
    raw: dict = field(default_factory=dict, repr=False)


class ProviderError(RuntimeError):
    pass


class Provider(Protocol):
    name: str
    model: str

    async def generate(
        self, *, system: str, prompt: str, images: list[Image], schema: dict, schema_name: str
    ) -> ProviderResult: ...


def require_env(*names: str) -> str:
    for name in names:
        if value := os.environ.get(name):
            return value
    raise ProviderError(f"Missing API key: set {' or '.join(names)}.")


def parse_json_text(text: str) -> Any:
    """Parse JSON that may come wrapped in a ```json fence or surrounded by prose."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
    return text


async def post_json(client: httpx.AsyncClient, url: str, *, headers: dict, body: dict, provider: str) -> dict:
    try:
        response = await client.post(url, headers=headers, json=body)
    except httpx.HTTPError as exc:
        raise ProviderError(f"{provider}: network error ({exc.__class__.__name__}).") from exc
    if response.status_code >= 400:
        detail = response.text[:300]
        raise ProviderError(f"{provider}: HTTP {response.status_code}: {detail}")
    return response.json()
