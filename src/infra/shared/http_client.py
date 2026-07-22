import logging
import aiohttp
from typing import Optional, Union, Dict, Any

logger = logging.getLogger(__name__)


class HttpClient:
    def __init__(
        self,
        timeout: int = 10,
        max_connections: int = 100,
        default_headers: Optional[Dict[str, str]] = None,
    ):
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_connections = max_connections
        self.default_headers = default_headers or {}
        self.connector = None
        self.session = None

    async def start(self):
        if self.session and not self.session.closed:
            return

        self.connector = aiohttp.TCPConnector(limit=self.max_connections)
        self.session = aiohttp.ClientSession(
            connector=self.connector,
            timeout=self.timeout,
            headers=self.default_headers,
        )

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
        self.session = None
        self.connector = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def _ensure_session(self):
        if self.session is None or self.session.closed:
            await self.start()

    async def request(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Union[Dict[str, Any], str, bytes]] = None,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Union[Dict[str, Any], str]:
        await self._ensure_session()
        request_headers = {**self.default_headers, **(headers or {})}

        try:
            async with self.session.request(
                method,
                url,
                params=params,
                data=data,
                json=json,
                headers=request_headers,
            ) as response:
                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "")

                if "application/json" in content_type:
                    return await response.json()
                return await response.text()

        except aiohttp.ClientResponseError as e:
            logger.error(f"HTTP error: {e.status} {e.message} url={url}")
            raise
        except aiohttp.ClientError as e:
            logger.error(f"Network error: {e} url={url}")
            raise

    async def get(self, url, params=None, headers=None):
        return await self.request("GET", url, params=params, headers=headers)

    async def post(self, url, data=None, json=None, headers=None):
        return await self.request("POST", url, data=data, json=json, headers=headers)

    async def put(self, url, data=None, json=None, headers=None):
        return await self.request("PUT", url, data=data, json=json, headers=headers)
