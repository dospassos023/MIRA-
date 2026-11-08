"""Sync facade for tests using HTTPX's supported in-process ASGI transport."""
import asyncio

import httpx


class TestClient:
    __test__ = False

    def __init__(self, app):
        self.runner = asyncio.Runner()
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        )

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        try:
            self.runner.run(self.client.aclose())
        finally:
            self.runner.close()

    def request(self, method, path, **kwargs):
        return self.runner.run(self.client.request(method, path, **kwargs))

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self.request("POST", path, **kwargs)

    def delete(self, path, **kwargs):
        return self.request("DELETE", path, **kwargs)
