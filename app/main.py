import time
import asyncio
from typing import Optional
from fastapi import FastAPI, Depends, Header, HTTPException, Response, status
from fastapi.responses import StreamingResponse, Response as FastAPIResponse
from fastapi.security import HTTPAuthorizationCredentials

from app.schemas import ChatCompletionRequest, ChatCompletionResponse
from app.services.auth import security, authenticate_and_authorize
from app.services.enrichment import enrichment_service
from app.services.rate_limiter import rate_limiter
from app.services.budget_service import budget_service
from app.services.resilience import resilience_engine, health_monitor
from app.services.tracing import tracing_service
from app.services.metrics import metrics_service
from app.services.alerting import alerting_service
from app.providers.factory import provider_factory
from app.routes import admin

app = FastAPI(
    title="Enterprise LLM Gateway - Phase 4",
    description="Unified Gateway with OpenTelemetry Tracing, Prometheus Metrics, Grafana Dashboards & Slack Alerting",
    version="4.0.0"
)

# Mount Admin API Router
app.include_router(admin.router)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "llm-gateway", "phase": 4}

@app.get("/metrics")
async def metrics_endpoint():
    content, content_type = metrics_service.export_metrics()
    return FastAPIResponse(content=content, media_type=content_type)

@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    response: Response,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_priority: str = Header("high", alias="X-Priority")
):
    start_time = time.time()

    # OpenTelemetry Root Span: request_receipt
    root_span = tracing_service.start_span("request_receipt", {
        "requested_model": request.model,
        "stream": request.stream,
        "priority": x_priority
    })

    # 1. Authenticate Team Key & Authorize Model Access
    auth_span = tracing_service.start_span("authentication")
    team = authenticate_and_authorize(credentials, requested_model=request.model)
    team_id = team["team_id"]
    auth_span.set_attribute("team_id", team_id)
    auth_span.end()

    # 2. Check Monthly Budget Cap
    monthly_budget = team.get("monthly_budget_usd", 100.0)
    can_proceed, current_spend, spend_percent, warning_flag = budget_service.check_budget_status(
        team_id, monthly_budget
    )
    if not can_proceed:
        metrics_service.record_error(team_id, request.model, "gateway", "BUDGET_CAP_EXCEEDED")
        await alerting_service.send_slack_alert("BUDGET_CAP_EXCEEDED", {
            "team_id": team_id,
            "team_name": team["name"],
            "monthly_budget": f"${monthly_budget:.2f}",
            "current_spend": f"${current_spend:.2f}"
        })
        root_span.end()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Monthly budget cap (${monthly_budget:.2f}) reached for team '{team['name']}'. Requests blocked."
        )

    if warning_flag:
        await alerting_service.send_slack_alert("BUDGET_WARNING_80_PERCENT", {
            "team_id": team_id,
            "team_name": team["name"],
            "spend_percent": f"{spend_percent:.1f}%"
        })

    # 3. Check Token Bucket Rate Limiting
    rl_span = tracing_service.start_span("rate_limit_check", {"team_id": team_id})
    limit_rpm = team.get("rate_limit_rpm", 60)
    allowed, retry_after, remaining_tokens = rate_limiter.check_rate_limit(
        team_id=team_id,
        limit_rpm=limit_rpm,
        priority=x_priority.lower(),
        requested_tokens=1
    )
    rl_span.end()

    if not allowed:
        metrics_service.record_error(team_id, request.model, "gateway", "RATE_LIMIT_EXCEEDED")
        root_span.end()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded for team '{team['name']}'. Retry after {retry_after} seconds.",
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(limit_rpm),
                "X-RateLimit-Remaining": "0"
            }
        )

    # 4. Enrich Request
    enrich_span = tracing_service.start_span("request_enrichment")
    enriched_request = enrichment_service.enrich_request(request, team_config=team)
    enrich_span.end()

    # 5. Streaming Passthrough
    if enriched_request.stream:
        provider = provider_factory.get_provider(request.model)
        root_span.end()
        return StreamingResponse(
            provider.stream_generate(enriched_request),
            media_type="text/event-stream"
        )

    # 6. Non-Streaming Response via Resilience Pipeline (OTel span: llm_api_call)
    api_span = tracing_service.start_span("llm_api_call", {"requested_model": request.model})
    try:
        res, final_model, exec_logs = await resilience_engine.execute_with_resilience(
            request=enriched_request,
            max_retries_per_model=2
        )
        api_span.set_attribute("final_model_served", final_model)
        api_span.end()
    except Exception as e:
        api_span.end()
        latency_sec = time.time() - start_time
        metrics_service.record_error(team_id, request.model, "gateway", "ALL_PROVIDERS_FAILED")
        metrics_service.record_request(team_id, request.model, "gateway", 503, latency_sec)
        root_span.end()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Resilience layer exhausted: {str(e)}"
        )

    # 7. Enrich output content with compliance disclaimer
    proc_span = tracing_service.start_span("response_processing")
    if res.choices:
        original_content = res.choices[0].message.content
        res.choices[0].message.content = enrichment_service.enrich_response_text(
            original_content, team_config=team
        )
    proc_span.end()

    # 8. Compute & Record Cost & Metrics
    prompt_tokens = res.usage.prompt_tokens
    completion_tokens = res.usage.completion_tokens
    req_cost = budget_service.calculate_request_cost(final_model, prompt_tokens, completion_tokens)
    new_total_spend = budget_service.record_spend(team_id, req_cost)

    latency_sec = time.time() - start_time
    latency_ms = round(latency_sec * 1000, 2)

    # Record Prometheus Metrics
    metrics_service.record_request(team_id, final_model, "provider", 200, latency_sec)
    metrics_service.record_tokens_and_cost(team_id, final_model, prompt_tokens, completion_tokens, req_cost)

    if final_model != request.model:
        metrics_service.record_fallback(team_id, request.model, final_model)

    # Update Health Status
    health_monitor.update_status(final_model, "HEALTHY", latency_ms, is_error=False)

    # 9. Inject Gateway Metadata & Headers
    response.headers["X-RateLimit-Limit"] = str(limit_rpm)
    response.headers["X-RateLimit-Remaining"] = str(remaining_tokens)

    res.gateway_metadata = {
        "team_id": team_id,
        "team_name": team["name"],
        "plan": team["plan"],
        "requested_model": request.model,
        "final_model_served": final_model,
        "fallback_triggered": bool(final_model != request.model),
        "priority_level": x_priority,
        "request_cost_usd": req_cost,
        "total_monthly_spend_usd": new_total_spend,
        "spend_percent": spend_percent,
        "budget_warning_80_percent": warning_flag,
        "latency_ms": latency_ms,
        "resilience_logs": exec_logs
    }

    # Finalize Root Span
    root_span.set_attribute("final_model", final_model)
    root_span.set_attribute("cost_usd", req_cost)
    root_span.set_attribute("total_tokens", prompt_tokens + completion_tokens)
    root_span.end()

    return res

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8080, reload=True)
