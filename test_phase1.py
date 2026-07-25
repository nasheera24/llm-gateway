import asyncio
import httpx
import json
from app.main import app

ALPHA_KEY = "sk-team-alpha-key-123"
BETA_KEY = "sk-team-beta-key-456"

async def test_invalid_auth():
    print("\n1. Testing Invalid API Key...")
    headers = {"Authorization": "Bearer invalid-key-xyz"}
    payload = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "Hello"}]
    }
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/v1/chat/completions", headers=headers, json=payload)
        print(f"Status: {res.status_code} (Expected 401)")
        print(f"Detail: {res.json()}")

async def test_unauthorized_model():
    print("\n2. Testing Restricted Model Authorization...")
    headers = {"Authorization": f"Bearer {BETA_KEY}"} # Beta only allows gpt-4o-mini & ollama
    payload = {
        "model": "claude-3-5-sonnet-20240620",
        "messages": [{"role": "user", "content": "Hello"}]
    }
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/v1/chat/completions", headers=headers, json=payload)
        print(f"Status: {res.status_code} (Expected 403)")
        print(f"Detail: {res.json()}")

async def test_openai_unified_call():
    print("\n3. Testing Unified Call to OpenAI (gpt-4o)...")
    headers = {"Authorization": f"Bearer {ALPHA_KEY}"}
    payload = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "What is 2+2?"}]
    }
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/v1/chat/completions", headers=headers, json=payload)
        print(f"Status: {res.status_code}")
        data = res.json()
        print(f"Response Model: {data.get('model')}")
        print(f"Output Content:\n{data['choices'][0]['message']['content']}")
        print(f"Gateway Metadata: {data.get('gateway_metadata')}")

async def test_anthropic_unified_call():
    print("\n4. Testing Unified Call to Anthropic (claude-3-5-sonnet)...")
    headers = {"Authorization": f"Bearer {ALPHA_KEY}"}
    payload = {
        "model": "claude-3-5-sonnet-20240620",
        "messages": [{"role": "user", "content": "Explain gravity in short."}]
    }
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/v1/chat/completions", headers=headers, json=payload)
        print(f"Status: {res.status_code}")
        data = res.json()
        print(f"Response Model: {data.get('model')}")
        print(f"Output Content:\n{data['choices'][0]['message']['content']}")
        print(f"Gateway Metadata: {data.get('gateway_metadata')}")

async def test_streaming_passthrough():
    print("\n5. Testing Real-time SSE Streaming Passthrough...")
    headers = {"Authorization": f"Bearer {ALPHA_KEY}"}
    payload = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "Tell me a joke."}],
        "stream": True
    }
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream("POST", "/v1/chat/completions", headers=headers, json=payload) as res:
            print(f"Status: {res.status_code}")
            print("Stream Chunks Received:")
            async for line in res.aiter_lines():
                if line.startswith("data: "):
                    print(f"  {line}")

async def main():
    await test_invalid_auth()
    await test_unauthorized_model()
    await test_openai_unified_call()
    await test_anthropic_unified_call()
    await test_streaming_passthrough()

if __name__ == "__main__":
    asyncio.run(main())
