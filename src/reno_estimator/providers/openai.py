"""OpenAI Responses API. Structured output via `text.format` json_schema.

`OPENAI_BASE_URL` lets you point it at any Responses-compatible endpoint.
"""

from __future__ import annotations

import os

import httpx

from .base import Image, ProviderError, ProviderResult, parse_json_text, post_json, require_env

DEFAULT_BASE_URL = "https://api.openai.com/v1"


class OpenAIProvider:
    name = "openai"

    def __init__(self, model: str, client: httpx.AsyncClient, max_output_tokens: int = 4096):
        self.model = model
        self._client = client
        self._max = max_output_tokens
        self._base = os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL).rstrip("/")

    async def generate(
        self, *, system: str, prompt: str, images: list[Image], schema: dict, schema_name: str
    ) -> ProviderResult:
        content: list[dict] = [
            {"type": "input_image", "image_url": f"data:{img.media_type};base64,{img.data_b64}"} for img in images
        ]
        content.append({"type": "input_text", "text": prompt})

        body = {
            "model": self.model,
            "instructions": system,
            "input": [{"role": "user", "content": content}],
            "max_output_tokens": self._max,
            # strict=False: pydantic schemas with optional fields aren't valid strict schemas.
            # The estimator validates the result anyway.
            "text": {"format": {"type": "json_schema", "name": schema_name, "schema": schema, "strict": False}},
        }
        headers = {"Authorization": f"Bearer {require_env('OPENAI_API_KEY')}"}
        raw = await post_json(self._client, f"{self._base}/responses", headers=headers, body=body, provider=self.name)

        texts = [
            part.get("text", "")
            for item in raw.get("output", [])
            if item.get("type") == "message"
            for part in item.get("content", [])
            if part.get("type") == "output_text"
        ]
        if not texts:
            raise ProviderError(f"{self.name}: empty response (status: {raw.get('status')}).")
        usage = raw.get("usage", {})
        return ProviderResult(
            data=parse_json_text("".join(texts)),
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            raw=raw,
        )
