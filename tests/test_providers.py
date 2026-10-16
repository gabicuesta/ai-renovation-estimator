import json

import httpx
import pytest

from reno_estimator.providers import Image, ProviderError, cost_usd, get_provider, parse_spec
from reno_estimator.providers.base import parse_json_text

SCHEMA = {"type": "object", "properties": {"a": {"type": "integer"}}}
IMG = Image(media_type="image/jpeg", data_b64="QUJD")


def client_returning(payload: dict, captured: list) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=payload)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def call(provider):
    return await provider.generate(system="sys", prompt="hola", images=[IMG], schema=SCHEMA, schema_name="submit")


async def test_anthropic_forces_tool_and_reads_input(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    captured = []
    payload = {
        "content": [{"type": "tool_use", "name": "submit", "input": {"a": 1}}],
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
    result = await call(get_provider("anthropic:claude-sonnet-5-5", client_returning(payload, captured)))

    body = json.loads(captured[0].content)
    assert captured[0].headers["x-api-key"] == "k"
    assert body["tool_choice"] == {"type": "tool", "name": "submit"}
    assert body["tools"][0]["input_schema"] == SCHEMA
    assert body["messages"][0]["content"][0]["source"]["data"] == "QUJD"
    assert result.data == {"a": 1} and result.input_tokens == 10 and result.output_tokens == 5


async def test_openai_uses_responses_api_json_schema(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    captured = []
    payload = {
        "status": "completed",
        "output": [{"type": "message", "content": [{"type": "output_text", "text": '{"a": 2}'}]}],
        "usage": {"input_tokens": 7, "output_tokens": 3},
    }
    result = await call(get_provider("openai:gpt-6.1-sol", client_returning(payload, captured)))

    body = json.loads(captured[0].content)
    assert str(captured[0].url) == "https://api.openai.com/v1/responses"
    assert body["text"]["format"]["type"] == "json_schema"
    assert body["input"][0]["content"][0]["image_url"].startswith("data:image/jpeg;base64,")
    assert result.data == {"a": 2} and result.input_tokens == 7


async def test_gemini_json_mode(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "k")
    captured = []
    payload = {
        "candidates": [{"content": {"parts": [{"text": '```json\n{"a": 3}\n```'}]}}],
        "usageMetadata": {"promptTokenCount": 9, "candidatesTokenCount": 4},
    }
    result = await call(get_provider("gemini:gemini-3.8-flash", client_returning(payload, captured)))

    body = json.loads(captured[0].content)
    assert captured[0].url.path.endswith("/gemini-3.8-flash:generateContent")
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["contents"][0]["parts"][0]["inline_data"]["data"] == "QUJD"
    assert result.data == {"a": 3} and result.output_tokens == 4


async def test_missing_key_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ProviderError, match="ANTHROPIC_API_KEY"):
        await call(get_provider("anthropic:", client_returning({}, [])))


async def test_http_errors_are_wrapped(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(429, text="rate limited")))
    with pytest.raises(ProviderError, match="HTTP 429"):
        await call(get_provider("openai:", client))


def test_parse_spec_defaults_and_errors():
    assert parse_spec("anthropic:") == ("anthropic", "claude-sonnet-5-5")
    assert parse_spec("OpenAI:gpt-6-luna") == ("openai", "gpt-6-luna")
    with pytest.raises(ProviderError):
        parse_spec("mistral:large")


def test_parse_json_text_variants():
    assert parse_json_text('{"a":1}') == {"a": 1}
    assert parse_json_text('Aquí tienes:\n```json\n{"a":1}\n```') == {"a": 1}
    assert parse_json_text('Resultado: {"a": 1} fin') == {"a": 1}
    assert parse_json_text("no json") == "no json"


def test_cost():
    assert cost_usd("claude-sonnet-5-5", 1_000_000, 100_000) == pytest.approx(3.0)
    assert cost_usd("unknown-model", 1, 1) is None
