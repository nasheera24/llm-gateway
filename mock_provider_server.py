import asyncio
import time
from fastapi import FastAPI, Request, Response, status
from fastapi.responses import StreamingResponse

app = FastAPI(title="Mock LLM Provider Server")

# Flags to simulate provider outages for testing
outage_flags = {
    "openai": False,
    "anthropic": False,
    "ollama": False
}

@app.post("/control/outage")
async def set_outage(provider: str, active: bool):
    outage_flags[provider.lower()] = active
    return {"status": "updated", "provider": provider, "outage_active": active}

@app.post("/openai/v1/chat/completions")
async def mock_openai(request: Request):
    if outage_flags["openai"]:
        return Response(content='{"error": "Simulated OpenAI 503 Outage"}', status_code=503)

    data = await request.json()
    if data.get("stream"):
        async def generate_chunks():
            yield 'data: {"id":"chatcmpl-mock","choices":[{"delta":{"content":"Mock "}}]}\n\n'
            await asyncio.sleep(0.01)
            yield 'data: {"id":"chatcmpl-mock","choices":[{"delta":{"content":"OpenAI chunk."}}]}\n\n'
            yield 'data: [DONE]\n\n'
        return StreamingResponse(generate_chunks(), media_type="text/event-stream")

    return {
        "id": "chatcmpl-mock-123",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": data.get("model", "gpt-4o"),
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": "This is a mock OpenAI response."},
            "finish_reason": "stop"
        }],
        "usage": {"prompt_tokens": 15, "completion_tokens": 10, "total_tokens": 25}
    }

@app.post("/anthropic/v1/messages")
async def mock_anthropic(request: Request):
    if outage_flags["anthropic"]:
        return Response(content='{"error": "Simulated Anthropic 503 Outage"}', status_code=503)

    data = await request.json()
    return {
        "id": "msg_mock_123",
        "type": "message",
        "role": "assistant",
        "model": data.get("model", "claude-3-5-sonnet-20240620"),
        "content": [{"type": "text", "text": "This is a mock Anthropic response."}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 15, "output_tokens": 10}
    }

@app.post("/ollama/api/chat")
async def mock_ollama(request: Request):
    if outage_flags["ollama"]:
        return Response(content='{"error": "Simulated Ollama Outage"}', status_code=503)

    data = await request.json()
    return {
        "model": "ollama/llama3.1",
        "created_at": "2026-07-26T00:00:00Z",
        "message": {"role": "assistant", "content": "This is a mock Ollama response."},
        "done": True,
        "prompt_eval_count": 15,
        "eval_count": 10
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9090)
