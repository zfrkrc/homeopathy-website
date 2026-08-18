import json
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ai_client import InsightMapAIClient, AIError  # noqa: E402
import app.ai_client as ai_client_mod  # noqa: E402


def _resp(status=200, body=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = body or {}
    return r


def test_client_missing_service_key():
    client = InsightMapAIClient(base_url="https://x", service_key="")
    with pytest.raises(AIError):
        client.generate_content("topic")


def test_generate_content_success(monkeypatch):
    monkeypatch.setattr(ai_client_mod.httpx, "post", MagicMock(return_value=_resp(200, {"ok": True, "result": {"content": "içerik"}})))
    client = InsightMapAIClient(base_url="https://x", service_key="sk-test")
    assert client.generate_content("t") == "içerik"
    call = ai_client_mod.httpx.post.call_args
    assert call[0][0] == "https://x/api/ai/task"
    assert call[1]["headers"]["X-InsightMap-Service-Key"] == "sk-test"
    assert call[1]["json"]["task"] == "content_generation"


def test_gateway_failure_raises(monkeypatch):
    monkeypatch.setattr(ai_client_mod.httpx, "post", MagicMock(return_value=_resp(500, {"detail": "model çöktü"})))
    client = InsightMapAIClient(base_url="https://x", service_key="sk")
    with pytest.raises(AIError):
        client.read_url("https://example.com")


def test_read_url_returns_text(monkeypatch):
    monkeypatch.setattr(ai_client_mod.httpx, "post", MagicMock(return_value=_resp(200, {"ok": True, "result": {"text": "sayfa"}})))
    client = InsightMapAIClient(base_url="https://x", service_key="sk")
    assert client.read_url("https://example.com") == "sayfa"


def test_ocr_returns_text(monkeypatch):
    monkeypatch.setattr(ai_client_mod.httpx, "post", MagicMock(return_value=_resp(200, {"ok": True, "result": {"text": "OCR"}})))
    client = InsightMapAIClient(base_url="https://x", service_key="sk")
    assert client.ocr("aGk=", "image/png") == "OCR"


def test_generate_image_returns_result(monkeypatch):
    monkeypatch.setattr(ai_client_mod.httpx, "post", MagicMock(return_value=_resp(200, {"ok": True, "result": {"id": "g1", "status": "waiting"}})))
    client = InsightMapAIClient(base_url="https://x", service_key="sk")
    assert client.generate_image("kedi")["id"] == "g1"


def test_invalid_response_ok_false(monkeypatch):
    monkeypatch.setattr(ai_client_mod.httpx, "post", MagicMock(return_value=_resp(200, {"ok": False})))
    client = InsightMapAIClient(base_url="https://x", service_key="sk")
    with pytest.raises(AIError):
        client.generate_content("t")


def test_network_error(monkeypatch):
    import httpx
    monkeypatch.setattr(ai_client_mod.httpx, "post", MagicMock(side_effect=httpx.ConnectError("bağlantı yok")))
    client = InsightMapAIClient(base_url="https://x", service_key="sk")
    with pytest.raises(AIError):
        client.generate_content("t")


def test_generate_content_gateway_failure_writes_error(monkeypatch, tmp_path):
    import app.main as main
    fake_client = MagicMock()
    fake_client.read_url.return_value = ""
    fake_client.generate_content.side_effect = AIError("model çöktü")
    monkeypatch.setattr(main, "ai_client", lambda: fake_client)
    monkeypatch.setattr(main, "AI_JOBS_DIR", str(tmp_path))
    main._generate_content("job1", "topic", "profesyonel", "500", "", None, "")
    with open(os.path.join(str(tmp_path), "job1.json")) as f:
        data = json.load(f)
    assert data["status"] == "done"
    assert data["result"].startswith("[HATA]")
