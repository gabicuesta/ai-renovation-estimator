"""Anthropic Messages API. Structured output by forcing a single tool call."""

from __future__ import annotations

import httpx

from .base import Image, ProviderError, ProviderResult, post_json, require_env

URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str, client: httpx.AsyncClient, max_tokens: int = 4096):
        self.model = model
        self._client = client
        self._max_tokens = max_tokens

    async def generate(
        self, *, system: str, prompt: str, images: list[Image], schema: dict, schema_name: str
    ) -> ProviderResult:
        content: list[dict] = [
            {"type": "image", "source": {"type": "base64", "media_type": img.media_type, "data": img.data_b64}}
            for img in images
        ]
        content.append({"type": "text", "text": prompt})

        body = {
            "model": self.model,
            "max_tokens": self._max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": content}],
            "tools": [{"name": schema_name, "description": "Submit the renovation estimate.", "input_schema": schema}],
            "tool_choice": {"type": "tool", "name": schema_name},
        }
        headers = {"x-api-key": require_env("ANTHROPIC_API_KEY"), "anthropic-version": API_VERSION}
        raw = await post_json(self._client, URL, headers=headers, body=body, provider=self.name)

        tool_use = next((b for b in raw.get("content", []) if b.get("type") == "tool_use"), None)
        if tool_use is None:
            raise ProviderError(f"{self.name}: the model did not return a tool call.")
        usage = raw.get("usage", {})
        return ProviderResult(
            data=tool_use.get("input"),
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            raw=raw,
        )
