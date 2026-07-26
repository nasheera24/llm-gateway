import asyncio
import time
import json
import httpx
from app.main import app
from app.services.circuit_breaker import circuit_breaker, CircuitState

ALPHA_KEY = "sk-team-alpha-key-123"
BETA_KEY = "sk-team-beta-key-456"

async def test_concurrent_rate_limiting():
    print("\n1. Testing Concurrent Rate Limiting under Load...")
    transport = httpx.ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {BETA_KEY}"} # Beta team RPM = 20
    payload = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "Concurrent test"}]}

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Send 30 concurrent requests
        tasks = [client.post("/v1/chat/completions", headers=headers, json=payload) for _ in range(30)]
        results = await asyncio.gather(*tasks)

        status_codes = [r.status_code for r in results]
        success_count = status_codes.count(200)
        blocked_count = status_codes.count(429)

        print(f"Total Requests: 30 | Allowed (200 OK): {success_count} | Blocked (429 Rate Limit): {blocked_count}")
        assert success_count <= 20
        assert blocked_count >= 10

async def test_streaming_sse_integrity():
    print("\n2. Testing Streaming SSE Response Passthrough Integrity...")
    transport = httpx.ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {ALPHA_KEY}"}
    payload = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "Stream test"}],
        "stream": True
    }

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream("POST", "/v1/chat/completions", headers=headers, json=payload) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")

            chunks = []
            async for line in response.aiter_lines():
                if line.strip():
                    chunks.append(line)

            print(f"Received SSE Stream Chunks Count: {len(chunks)}")
            print(f"Sample SSE Chunk: {chunks[0]}")
            assert any("[DONE]" in chunk for chunk in chunks)

async def test_circuit_breaker_and_fallback():
    print("\n3. Testing Circuit Breaker & Automatic Fallback...")
    transport = httpx.ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {ALPHA_KEY}"}
    payload = {"model": "gpt-4o", "messages": [{"role": "user", "content": "Fallback test"}]}

    # Force gpt-4o circuit breaker OPEN
    circuit_breaker.record_failure("gpt-4o", "Integration test outage")
    circuit_breaker.record_failure("gpt-4o", "Integration test outage")
    circuit_breaker.record_failure("gpt-4o", "Integration test outage")

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/v1/chat/completions", headers=headers, json=payload)
        data = res.json()
        meta = data.get("gateway_metadata", {})
        print(f"Requested: {meta.get('requested_model')} | Served: {meta.get('final_model_served')}")
        assert meta.get("fallback_triggered") is True
        assert meta.get("final_model_served") == "claude-3-5-sonnet-20240620"

    # Reset circuit breaker
    circuit_breaker.record_success("gpt-4o")

async def main():
    await test_concurrent_rate_limiting()
    await test_streaming_sse_integrity()
    await test_circuit_breaker_and_fallback()

if __name__ == "__main__":
    asyncio.run(main())
