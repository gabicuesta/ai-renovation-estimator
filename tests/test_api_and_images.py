import base64
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image as PILImage

from reno_estimator import api
from reno_estimator.images import MAX_SIDE, ImageError, prepare


def png_bytes(w=3000, h=2000) -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", (w, h), (200, 120, 80)).save(buf, format="PNG")
    return buf.getvalue()


def test_images_are_downscaled_and_converted():
    [img] = prepare([png_bytes()])
    decoded = PILImage.open(io.BytesIO(base64.b64decode(img.data_b64)))
    assert img.media_type == "image/jpeg"
    assert max(decoded.size) == MAX_SIDE


def test_invalid_images_are_rejected():
    with pytest.raises(ImageError, match="Photo 1"):
        prepare([b"not an image"])
    with pytest.raises(ImageError, match="Up to"):
        prepare([png_bytes(10, 10)] * 7)


@pytest.fixture
def client(monkeypatch, draft, fake_provider):
    provider = fake_provider(draft)
    monkeypatch.setattr(api, "get_provider", lambda spec, http: provider)
    with TestClient(api.create_app()) as c:
        c.provider = provider
        yield c


def test_index_page(client):
    r = client.get("/")
    assert r.status_code == 200 and "Presupuestador" in r.text


def test_estimate_endpoint_with_photo(client):
    r = client.post(
        "/api/estimate",
        data={"description": "Reformar el baño completo", "province": "Madrid", "area_m2": "5"},
        files=[("photos", ("bano.png", png_bytes(), "image/png"))],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["subtotal_low"] > 0 and body["usage"]["provider"] == "fake"
    assert len(client.provider.calls[0]["images"]) == 1


def test_estimate_endpoint_validation(client):
    r = client.post("/api/estimate", data={"description": "corto"})
    assert r.status_code == 422
