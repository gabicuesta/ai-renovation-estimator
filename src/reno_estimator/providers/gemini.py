"""Google Gemini generateContent API. JSON mode, with the schema given in the prompt.

Gemini's native response schema supports only a subset of JSON Schema, so instead of
rewriting the schema we ask for JSON and validate it ourselves like for every provider.
"""

from __future__ import annotations

import json

import httpx

from .base import Image, ProviderError, ProviderResult, parse_json_text, post_json, require_env

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider:
    name = "gemini"

    def __init__(self, model: str, client: httpx.AsyncClient, max_output_tokens: int = 4096):
        self.model = model
        self._client = client
        self._max = max_output_tokens

    async def generate(
        self, *, system: str, prompt: str, images: list[Image], schema: dict, schema_name: str
    ) -> ProviderResult:
        parts: list[dict] = [{"inline_data": {"mime_type": img.media_type, "data": img.data_b64}} for img in images]
        parts.append(
            {
                "text": f"{prompt}\n\nRespond with a single JSON object ({schema_name}) that conforms to this "
                f"JSON Schema:\n{json.dumps(schema, ensure_ascii=False)}"
            }
        )
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": self._max},
        }
        headers = {"x-goog-api-key": require_env("GEMINI_API_KEY", "GOOGLE_API_KEY")}
        url = f"{BASE_URL}/{self.model}:generateContent"
        raw = await post_json(self._client, url, headers=headers, body=body, provider=self.name)

        candidates = raw.get("candidates") or []
        if not candidates:
            reason = (raw.get("promptFeedback") or {}).get("blockReason", "no candidates")
            raise ProviderError(f"{self.name}: empty response ({reason}).")
        text = "".join(p.get("text", "") for p in candidates[0].get("content", {}).get("parts", []))
        usage = raw.get("usageMetadata", {})
        return ProviderResult(
            data=parse_json_text(text),
            input_tokens=usage.get("promptTokenCount", 0),
            output_tokens=usage.get("candidatesTokenCount", 0),
            raw=raw,
        )
