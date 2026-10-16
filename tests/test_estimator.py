import pytest

from reno_estimator.estimator import DRAFT_SCHEMA, EstimationError, build_prompt, estimate
from reno_estimator.schema import EstimateRequest

REQ = EstimateRequest(description="Reformar el baño completo", province="Madrid", area_m2=5)


async def test_happy_path(draft, fake_provider):
    provider = fake_provider(draft)
    est = await estimate(REQ, provider)

    assert est.subtotal_low > 0
    assert est.usage.attempts == 1
    assert est.usage.input_tokens == 1000
    assert "Madrid" in provider.calls[0]["prompt"]


async def test_repairs_invalid_output_once(draft, fake_provider):
    broken = {**draft, "line_items": [{**draft["line_items"][0], "chapter": "jardineria"}]}
    provider = fake_provider(broken, draft)
    est = await estimate(REQ, provider)

    assert est.usage.attempts == 2
    assert est.usage.input_tokens == 2000  # both attempts are accounted for
    assert "no cumplía el esquema" in provider.calls[1]["prompt"]
    assert "chapter" in provider.calls[1]["prompt"]


async def test_accepts_json_as_text(draft, fake_provider):
    import json

    est = await estimate(REQ, fake_provider(json.dumps(draft)))
    assert len(est.line_items) == 3


async def test_gives_up_after_max_attempts(fake_provider):
    with pytest.raises(EstimationError, match="2 attempts"):
        await estimate(REQ, fake_provider({"nope": 1}, "not json"))


def test_schema_is_self_contained():
    assert "$ref" not in str(DRAFT_SCHEMA) and "$defs" not in DRAFT_SCHEMA
    assert "line_items" in DRAFT_SCHEMA["required"]


def test_prompt_without_photos_says_so():
    prompt = build_prompt(EstimateRequest(description="Pintar el salón entero"), n_images=0)
    assert "No hay fotos" in prompt and "precios medios de España" in prompt


def test_dotenv_loader(tmp_path, monkeypatch):
    from reno_estimator.env import load_dotenv

    (tmp_path / ".env").write_text('# c\nX_TEST_KEY="abc"\nEMPTY=\nX_KEEP=new\n')
    monkeypatch.setenv("X_KEEP", "old")
    monkeypatch.delenv("X_TEST_KEY", raising=False)
    load_dotenv(tmp_path / ".env")
    import os

    assert os.environ["X_TEST_KEY"] == "abc" and os.environ["X_KEEP"] == "old" and "EMPTY" not in os.environ
