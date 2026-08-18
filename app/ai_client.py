"""InsightMap merkezi AI Gateway client.

Bu modül, doğrudan model/endpoint seçimi YAPMAZ — tüm AI çağrıları merkezi
`POST /api/ai/task` üzerinden gider (tenant identity service key'den gelir).

Service key yalnızca environment'dan okunur; frontend'e, log'a ve repo'ya ASLA
yazılmaz. AI servisi hata verirse site/uygulama çalışmaya devam eder (AIError).
"""
import os

import httpx

INSIGHTMAP_AI_URL = os.environ.get("INSIGHTMAP_AI_URL", "https://insightmap.tr")
INSIGHTMAP_AI_SERVICE_KEY = os.environ.get("INSIGHTMAP_AI_SERVICE_KEY", "")


class AIError(Exception):
    """AI gateway çağrısı başarısız olduğunda kullanıcıya anlaşılır hata için."""


class InsightMapAIClient:
    def __init__(self, base_url=None, service_key=None, timeout=180.0):
        self.base_url = (base_url or INSIGHTMAP_AI_URL).rstrip("/")
        self.service_key = service_key if service_key is not None else INSIGHTMAP_AI_SERVICE_KEY
        self.timeout = timeout

    def _headers(self):
        if not self.service_key:
            raise AIError("INSIGHTMAP_AI_SERVICE_KEY tanımlı değil")
        return {
            "X-InsightMap-Service-Key": self.service_key,
            "Content-Type": "application/json",
        }

    def _task(self, task, payload, external_job_id=""):
        body = {"task": task, "payload": payload}
        if external_job_id:
            body["external_job_id"] = external_job_id
        try:
            resp = httpx.post(
                f"{self.base_url}/api/ai/task",
                json=body,
                headers=self._headers(),
                timeout=self.timeout,
            )
        except httpx.HTTPError as e:
            raise AIError(f"AI servisine ulaşılamadı: {e}")

        if resp.status_code != 200:
            detail = ""
            try:
                detail = resp.json().get("detail", "")
            except Exception:
                detail = resp.text[:200]
            raise AIError(f"AI task '{task}' başarısız ({resp.status_code}): {detail}")

        data = resp.json()
        if not data.get("ok"):
            raise AIError(f"AI task '{task}' başarısız")
        return data

    def generate_content(self, topic, tone="profesyonel", length="500", context=None):
        payload = {"topic": topic, "tone": tone, "length": length}
        if context:
            payload["context"] = context
        data = self._task("content_generation", payload)
        return (data.get("result") or {}).get("content", "")

    def read_url(self, url):
        data = self._task("url_read", {"url": url})
        return (data.get("result") or {}).get("text", "")

    def ocr(self, image_base64, mime_type="image/png"):
        data = self._task("ocr", {"image_base64": image_base64, "mime_type": mime_type})
        return (data.get("result") or {}).get("text", "")

    def generate_image(self, prompt, width=1024, height=1024, style=None, steps=None, enhance_prompt=None):
        payload = {"prompt": prompt, "width": width, "height": height}
        if style:
            payload["style"] = style
        if steps:
            payload["steps"] = steps
        if enhance_prompt is not None:
            payload["enhance_prompt"] = enhance_prompt
        data = self._task("image_generation", payload)
        return data.get("result") or {}


_client = None


def ai_client() -> InsightMapAIClient:
    """Module-level singleton (timeout/URL bir kez okunur)."""
    global _client
    if _client is None:
        _client = InsightMapAIClient()
    return _client
