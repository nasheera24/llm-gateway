import time
from typing import Optional
from fastapi import FastAPI, Depends, Header, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials

from app.schemas import ChatCompletionRequest, ChatCompletionResponse
from app.services.auth import security, authenticate_and_authorize
from app.services.enrichment import enrichment_service
from app.services.rate_limiter import rate_limiter
from app.services.budget_service import budget_service
from app.providers.factory import provider_factory
from app.routes import admin

app = FastAPI(
    title="Enterprise LLM Gateway - Phase 2",
    description="Unified Gateway with Token-Bucket Rate Limiting, Budget Caps & Admin API",
    version="2.0.0"
)

# Mount Admin API Router
app.include_router(admin.router)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "llm-gateway", "phase": 2}

@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    response: Response,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_priority: str = Header("high", alias="X-Priority")
):
    start_time = time.time()

    # 1. Authenticate Team Key & Authorize Model Access
    team = authenticate_and_authorize(credentials, requested_model=request.model)
    team_id = team["team_id"]

    # 2. Check Monthly Budget Cap
    monthly_budget = team.get("monthly_budget_usd", 100.0)
    can_proceed, current_spend, spend_percent, warning_flag = budget_service.check_budget_status(
        team_id, monthly_budget
    )
    if not can_proceed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Monthly budget cap (${monthly_budget:.2f}) reached for team '{team['name']}'. Current spend: ${current_spend:.2f}. Requests blocked."
        )

    # 3. Check Token Bucket Rate Limiting (With Priority Reservation)
    limit_rpm = team.get("rate_limit_rpm", 60)
    allowed, retry_after, remaining_tokens = rate_limiter.check_rate_limit(
        team_id=team_id,
        limit_rpm=limit_rpm,
        priority=x_priority.lower(),
        requested_tokens=1
    )

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded for team '{team['name']}'. Retry after {retry_after} seconds.",
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(limit_rpm),
                "X-RateLimit-Remaining": "0"
            }
        )


    # 4. Enrich Request (System Prompts, Disclaimers)
    enriched_request = enrichment_service.enrich_request(request, team_config=team)

    # 5. Route to Provider Adapter
    provider = provider_factory.get_provider(request.model)

    # 6. Streaming Passthrough
    if enriched_request.stream:
        return StreamingResponse(
            provider.stream_generate(enriched_request),
            media_type="text/event-stream"
        )

    # 7. Non-Streaming Response
    res: ChatCompletionResponse = await provider.generate(enriched_request)

    # 8. Enrich output content with compliance disclaimer
    if res.choices:
        original_content = res.choices[0].message.content
        res.choices[0].message.content = enrichment_service.enrich_response_text(
            original_content, team_config=team
        )

    # 9. Compute & Record Cost
    prompt_tokens = res.usage.prompt_tokens
    completion_tokens = res.usage.completion_tokens
    req_cost = budget_service.calculate_request_cost(request.model, prompt_tokens, completion_tokens)
    new_total_spend = budget_service.record_spend(team_id, req_cost)

    # Re-evaluate warning flag after recording new spend
    _, _, updated_spend_percent, updated_warning_flag = budget_service.check_budget_status(team_id, monthly_budget)

    # 10. Inject Gateway Metadata & Headers
    latency_ms = round((time.time() - start_time) * 1000, 2)
    response.headers["X-RateLimit-Limit"] = str(limit_rpm)
    response.headers["X-RateLimit-Remaining"] = str(remaining_tokens)

    res.gateway_metadata = {
        "team_id": team_id,
        "team_name": team["name"],
        "plan": team["plan"],
        "provider_served": provider.__class__.__name__,
        "priority_level": x_priority,
        "request_cost_usd": req_cost,
        "total_monthly_spend_usd": new_total_spend,
        "spend_percent": updated_spend_percent,
        "budget_warning_80_percent": updated_warning_flag,
        "latency_ms": latency_ms
    }

    return res

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8080, reload=True)
