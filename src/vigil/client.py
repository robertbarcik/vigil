"""Async OpenRouter API client."""

from __future__ import annotations

import asyncio
import logging

import httpx

from vigil.config import get_api_key

logger = logging.getLogger(__name__)

OPENROUTER_BASE = "https://openrouter.ai/api/v1"


class VigilClient:
    """Async client for OpenRouter chat completions."""

    def __init__(self, api_key: str | None = None, base_url: str = OPENROUTER_BASE):
        self.api_key = api_key or get_api_key()
        self.base_url = base_url
        self._http: httpx.AsyncClient | None = None

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "HTTP-Referer": "https://github.com/robertbarcik/vigil",
                    "X-Title": "Vigil",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(120.0, connect=30.0),
            )
        return self._http

    async def chat(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 1.0,
        system_prompt: str | None = None,
    ) -> dict:
        """Send a chat completion request. Returns the full response dict."""
        # Strip common prefixes — OpenRouter model IDs are like "vendor/model"
        if model.startswith("openrouter/"):
            model = model[len("openrouter/"):]

        payload: dict = {
            "model": model,
            "messages": [],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if system_prompt:
            payload["messages"].append({"role": "system", "content": system_prompt})
        payload["messages"].extend(messages)

        http = await self._get_http()
        resp = await http.post("/chat/completions", json=payload)
        if resp.status_code >= 400:
            logger.error(f"API error {resp.status_code}: {resp.text}")
        resp.raise_for_status()
        return resp.json()

    async def chat_with_retry(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 1.0,
        system_prompt: str | None = None,
        retries: int = 5,
    ) -> dict:
        """Chat with exponential backoff retry."""
        last_error: Exception | None = None
        for attempt in range(retries):
            try:
                return await self.chat(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system_prompt=system_prompt,
                )
            except (httpx.HTTPStatusError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                last_error = e
                wait = min(2**attempt * 2, 60)
                logger.warning(f"Attempt {attempt + 1}/{retries} failed: {e}. Retrying in {wait}s...")
                await asyncio.sleep(wait)
        raise RuntimeError(f"All {retries} attempts failed. Last error: {last_error}")

    @staticmethod
    def extract_content(response: dict) -> str:
        """Extract text content from an OpenRouter response."""
        choices = response.get("choices", [])
        if not choices:
            return ""
        return choices[0].get("message", {}).get("content", "")

    async def close(self):
        if self._http and not self._http.is_closed:
            await self._http.aclose()
