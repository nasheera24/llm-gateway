import time
from typing import Optional
from fastapi import FastAPI, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials

from app.schemas import ChatCompletionRequest, ChatCompletionResponse
from app.services.auth import security, authenticate_and_authorize
from app.services.enrichment import enrichment_service
from app.providers.factory import provider_factory

app = FastAPI(
    title="Enterprise LLM Gateway - Phase 1",
    description="Unified API Gateway normalizing requests across OpenAI, Anthropic, and Ollama",
    version="1.0.0"
)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "llm-gateway", "phase": 1}

@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):

    start_time = time.time()

    # 1. Authenticate Team Key & Authorize Model Access
    team = authenticate_and_authorize(credentials, requested_model=request.model)

    # 2. Enrich Request (System Prompts, Disclaimers)
    enriched_request = enrichment_service.enrich_request(request, team_config=team)

    # 3. Route to Corresponding Provider
    provider = provider_factory.get_provider(request.model)

    # 4. Handle Streaming vs Non-Streaming
    if enriched_request.stream:
        # Return transparent SSE streaming passthrough
        return StreamingResponse(
            provider.stream_generate(enriched_request),
            media_type="text/event-stream"
        )

    # Non-Streaming Response
    response: ChatCompletionResponse = await provider.generate(enriched_request)

    # Enrich output content with compliance disclaimer
    if response.choices:
        original_content = response.choices[0].message.content
        response.choices[0].message.content = enrichment_service.enrich_response_text(
            original_content, team_config=team
        )

    # Inject Gateway Metadata
    latency_ms = round((time.time() - start_time) * 1000, 2)
    response.gateway_metadata = {
        "team_id": team["team_id"],
        "team_name": team["name"],
        "plan": team["plan"],
        "provider_served": provider.__class__.__name__,
        "latency_ms": latency_ms
    }

    return response

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
