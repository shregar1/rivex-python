"""``rivex.utilities.webhook`` — generic HTTP webhook delivery utility."""

from __future__ import annotations

from typing import Any, Dict, Optional

from rivex.utilities.abstraction import LayeredUtility


class WebhookUtility(LayeredUtility):
    """Generic HTTP webhook POST utility (Slack, Teams, generic endpoints, ...)."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)

    async def post(
        self,
        url: str,
        payload: Dict[str, Any],
        *,
        timeout_seconds: float = 10.0,
        headers: Optional[Dict[str, str]] = None,
        method: str = "POST",
    ) -> Dict[str, Any]:
        """Send an HTTP request to ``url`` and return a normalized result dict.

        Result shape: ``{"ok": bool, "status_code": int, "body": Any, "url": str, "error"?: str}``.
        Transport errors return ``status_code=0`` with an ``error`` field instead
        of raising so callers can branch on ``ok``.
        """
        if not url:
            raise ValueError("url is required")
        if not isinstance(payload, dict):
            raise ValueError("payload must be a dict")

        try:
            import httpx
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Webhook delivery requires the 'httpx' package. "
                "Install it via `pip install httpx`."
            ) from exc

        request_headers = {"Content-Type": "application/json"}
        if headers:
            request_headers.update(headers)

        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.request(
                    method=method.upper(),
                    url=url,
                    json=payload,
                    headers=request_headers,
                )
            try:
                body: Any = response.json()
            except ValueError:
                body = response.text
            return {
                "ok": response.is_success,
                "status_code": response.status_code,
                "body": body,
                "url": url,
            }
        except httpx.HTTPError as exc:
            return {
                "ok": False,
                "status_code": 0,
                "body": None,
                "url": url,
                "error": str(exc),
            }

    async def post_json(self, url: str, payload: Dict[str, Any], **kwargs: Any) -> int:
        """Convenience: POST and return the status code (``0`` on transport error)."""
        result = await self.post(url, payload, **kwargs)
        return int(result.get("status_code", 0))

    @property
    def label(self) -> str:
        """Returns the class name."""
        return "WebhookUtility"


__all__ = ["WebhookUtility"]
