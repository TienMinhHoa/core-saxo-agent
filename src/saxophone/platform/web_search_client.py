"""Small Tavily HTTP adapter kept outside the agent domain."""

from __future__ import annotations

import httpx


class TavilySearchClient:
    """Implement the provider port expected by ``WebSearchAdapter``."""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        api_key: str,
        base_url: str = "https://api.tavily.com",
        timeout_seconds: float = 20.0,
    ) -> None:
        if not isinstance(api_key, str) or not api_key.strip() or any(ord(c) < 32 for c in api_key):
            raise ValueError("api_key must be a safe non-empty value")
        if not callable(getattr(http_client, "post", None)):
            raise TypeError("http_client must provide post")
        self._http_client = http_client
        self._api_key = api_key.strip()
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    async def search(self, query: str, *, limit: int) -> object:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must not be blank")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        try:
            response = await self._http_client.post(
                f"{self._base_url}/search",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "query": query.strip(),
                    "max_results": limit,
                    "include_answer": False,
                    "include_raw_content": False,
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as error:
            raise RuntimeError(f"Tavily search failed with HTTP {error.response.status_code}") from None
        except httpx.HTTPError as error:
            raise RuntimeError("Tavily search transport failed") from None
        except ValueError:
            raise ValueError("Tavily search returned invalid JSON") from None
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise ValueError("Tavily search response must contain a results list")
        return {
            "results": [
                {
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "snippet": item.get("content") or item.get("snippet"),
                    "content": item.get("raw_content") or item.get("content"),
                }
                for item in payload["results"]
                if isinstance(item, dict)
            ]
        }


__all__ = ["TavilySearchClient"]
