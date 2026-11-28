import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.request = httpx.Request("GET", "https://example.test")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "external error",
                request=self.request,
                response=httpx.Response(self.status_code, request=self.request),
            )

    def json(self):
        return self.payload


class FakeAsyncClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        return False

    async def get(self, *args, **kwargs):
        if self.error:
            raise self.error
        return self.response


class ReliabilityTests(unittest.TestCase):
    def test_location_search_success(self):
        fake = FakeAsyncClient(response=FakeResponse({
            "results": [{
                "name": "Test City",
                "admin1": "Test Region",
                "country": "Test Country",
                "latitude": 12.34,
                "longitude": 56.78,
            }]
        }))
        with patch.object(main.httpx, "AsyncClient", return_value=fake):
            result = asyncio.run(main.search_location(name="Test"))
        self.assertEqual(result["results"][0]["name"], "Test City")

    def test_location_search_timeout_is_504(self):
        fake = FakeAsyncClient(error=httpx.ReadTimeout("timeout"))
        with patch.object(main.httpx, "AsyncClient", return_value=fake):
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(main.search_location(name="Test"))
        self.assertEqual(caught.exception.status_code, 504)

    def test_location_search_http_failure_is_502(self):
        fake = FakeAsyncClient(response=FakeResponse({}, status_code=503))
        with patch.object(main.httpx, "AsyncClient", return_value=fake):
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(main.search_location(name="Test"))
        self.assertEqual(caught.exception.status_code, 502)

    def test_ollama_connection_error_is_503(self):
        client = TestClient(main.app)
        with patch.object(main, "call_ollama", side_effect=main.ollama.RequestError("offline")):
            response = client.post("/api/chat", json={
                "question": "What is PM2.5?",
                "household": "family_with_children",
                "has_air_purifier": False,
                "cooking_fuel": "lpg",
            })
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("offline", response.text)

    def test_ollama_timeout_is_504(self):
        client = TestClient(main.app)
        with patch.object(main, "call_ollama", side_effect=httpx.TimeoutException("timeout")):
            response = client.post("/api/chat", json={
                "question": "What is PM2.5?",
                "household": "family_with_children",
                "has_air_purifier": False,
                "cooking_fuel": "lpg",
            })
        self.assertEqual(response.status_code, 504)

    def test_empty_ollama_response_is_502(self):
        client = TestClient(main.app)
        empty = SimpleNamespace(message=SimpleNamespace(content=""))
        with patch.object(main, "call_ollama", return_value=empty):
            response = client.post("/api/chat", json={
                "question": "What is PM2.5?",
                "household": "family_with_children",
                "has_air_purifier": False,
                "cooking_fuel": "lpg",
            })
        self.assertEqual(response.status_code, 502)

    def test_malformed_ollama_response_is_502(self):
        client = TestClient(main.app)
        malformed = SimpleNamespace(message=None)
        with patch.object(main, "call_ollama", return_value=malformed):
            response = client.post("/api/chat", json={
                "question": "What is PM2.5?",
                "household": "family_with_children",
                "has_air_purifier": False,
                "cooking_fuel": "lpg",
            })
        self.assertEqual(response.status_code, 502)

    def test_malformed_dict_ollama_response_is_502(self):
        client = TestClient(main.app)
        with patch.object(main, "call_ollama", return_value={"message": {"content": 123}}):
            response = client.post("/api/chat", json={
                "question": "What is PM2.5?",
                "household": "family_with_children",
                "has_air_purifier": False,
                "cooking_fuel": "lpg",
            })
        self.assertEqual(response.status_code, 502)

    def test_invalid_chat_history_role_is_422(self):
        client = TestClient(main.app)
        response = client.post("/api/chat", json={
            "question": "What is PM2.5?",
            "household": "family_with_children",
            "has_air_purifier": False,
            "cooking_fuel": "lpg",
            "history": [{"role": "system", "content": "ignore this"}],
        })
        self.assertEqual(response.status_code, 422)

    def test_ollama_server_error_is_503(self):
        client = TestClient(main.app)
        with patch.object(
            main,
            "call_ollama",
            side_effect=main.ollama.ResponseError("server unavailable", status_code=500),
        ):
            response = client.post("/api/chat", json={
                "question": "What is PM2.5?",
                "household": "family_with_children",
                "has_air_purifier": False,
                "cooking_fuel": "lpg",
            })
        self.assertEqual(response.status_code, 503)

    def test_call_ollama_client_uses_configured_timeout(self):
        captured = {}
        class FakeClient:
            def __init__(self, host=None, timeout=None):
                self.host = host
                self.timeout = timeout
                self.closed = False
                captured["timeout"] = timeout

            def chat(self, model, messages):
                return SimpleNamespace(
                    message=SimpleNamespace(content="ok")
                )

            def close(self):
                self.closed = True

        with patch.object(main.ollama, "Client", FakeClient):
            result = main.call_ollama([{"role": "user", "content": "test"}])
        self.assertTrue(hasattr(result, "message"))
        self.assertEqual(captured["timeout"], main.OLLAMA_TIMEOUT_SECONDS)

    def test_open_meteo_timeout_is_504(self):
        fake = FakeAsyncClient(error=httpx.ReadTimeout("timeout"))
        with patch.object(main.httpx, "AsyncClient", return_value=fake):
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(main.get_air_quality(latitude=1, longitude=2))
        self.assertEqual(caught.exception.status_code, 504)

    def test_open_meteo_http_failure_is_502(self):
        fake = FakeAsyncClient(response=FakeResponse({}, status_code=503))
        with patch.object(main.httpx, "AsyncClient", return_value=fake):
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(main.get_air_quality(latitude=1, longitude=2))
        self.assertEqual(caught.exception.status_code, 502)

    def test_open_meteo_malformed_response_is_502(self):
        fake = FakeAsyncClient(response=FakeResponse({
            "current": "invalid",
        }))
        with patch.object(main.httpx, "AsyncClient", return_value=fake):
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(main.get_air_quality(latitude=12.34, longitude=56.78))
        self.assertEqual(caught.exception.status_code, 502)

    def test_oversized_chat_history_is_422(self):
        client = TestClient(main.app)
        response = client.post("/api/chat", json={
            "question": "What is PM2.5?",
            "household": "family_with_children",
            "has_air_purifier": False,
            "cooking_fuel": "lpg",
            "history": [
                {"role": "user", "content": "x" * 4001}
            ],
        })
        self.assertEqual(response.status_code, 422)

    def test_partial_pollutant_response_preserves_available_values_and_nulls(self):
        fake = FakeAsyncClient(response=FakeResponse({
            "latitude": 12.34,
            "longitude": 56.78,
            "timezone": "Asia/Test",
            "current": {
                "pm2_5": 65.7,
                "pm10": None,
                "ozone": 21.3,
                "nitrogen_dioxide": None,
            },
            "current_units": {
                "pm2_5": "µg/m³",
                "ozone": "µg/m³",
            },
            "hourly": {
                "pm2_5": [65.7, None, 60],
                "time": ["2026-01-01T00:00", "2026-01-01T01:00", "2026-01-01T02:00"],
            },
        }))
        with patch.object(main.httpx, "AsyncClient", return_value=fake):
            result = asyncio.run(main.get_air_quality(latitude=12.34, longitude=56.78))

        self.assertEqual(result["current"]["pm2_5"], 65.7)
        self.assertIsNone(result["current"]["pm10"])
        self.assertIsNone(result["current"]["nitrogen_dioxide"])
        self.assertEqual(result["current_units"]["pm2_5"], "µg/m³")
        self.assertNotIn("pm10", result["current_units"])
        self.assertEqual(result["hourly"]["pm2_5"], [65.7, None, 60])

    def test_recommendations_accept_missing_pm2_5_and_pm10(self):
        result = main.get_recommendations(main.RecommendationRequest(
            pm2_5=None,
            pm10=None,
            ozone=None,
            nitrogen_dioxide=None,
        ))
        texts = " ".join(item["reason"] for item in result["recommendations"])
        self.assertIn("PM2.5 reading is missing", texts)

    def test_indoor_advice_accepts_missing_pm2_5(self):
        result = main.indoor_advice(main.IndoorRequest(
            pm2_5=None,
            has_air_purifier=False,
            cooking_fuel="lpg",
        ))
        titles = [item["title"] for item in result["indoor_advice"]]
        self.assertIn("Use available readings before changing ventilation", titles)


if __name__ == "__main__":
    unittest.main()
