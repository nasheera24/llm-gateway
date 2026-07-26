from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST
)

# Prometheus Metrics Definitions
REQUESTS_TOTAL = Counter(
    "llm_gateway_requests_total",
    "Total HTTP requests handled by the gateway",
    ["team_id", "model", "provider", "status"]
)

ERRORS_TOTAL = Counter(
    "llm_gateway_errors_total",
    "Total errors encountered by gateway",
    ["team_id", "model", "provider", "error_type"]
)

LATENCY_HISTOGRAM = Histogram(
    "llm_gateway_latency_seconds",
    "Request latency in seconds",
    ["provider", "model"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
)

TOKENS_TOTAL = Counter(
    "llm_gateway_tokens_total",
    "Total tokens consumed",
    ["token_type", "team_id", "model"]
)

COST_USD_TOTAL = Counter(
    "llm_gateway_cost_usd_total",
    "Total cost in USD incurred per team and model",
    ["team_id", "model"]
)

FALLBACK_TRIGGERS_TOTAL = Counter(
    "llm_gateway_fallback_triggers_total",
    "Total times automatic model failover was triggered",
    ["team_id", "requested_model", "final_model"]
)

CIRCUIT_BREAKER_STATE = Gauge(
    "llm_gateway_circuit_breaker_state",
    "Circuit breaker state per model (0=CLOSED, 1=HALF_OPEN, 2=OPEN)",
    ["model"]
)

class MetricsService:
    @staticmethod
    def record_request(team_id: str, model: str, provider: str, status_code: int, latency_sec: float):
        status_str = str(status_code)
        REQUESTS_TOTAL.labels(team_id=team_id, model=model, provider=provider, status=status_str).inc()
        LATENCY_HISTOGRAM.labels(provider=provider, model=model).observe(latency_sec)

    @staticmethod
    def record_tokens_and_cost(team_id: str, model: str, prompt_tokens: int, completion_tokens: int, cost_usd: float):
        TOKENS_TOTAL.labels(token_type="input", team_id=team_id, model=model).inc(prompt_tokens)
        TOKENS_TOTAL.labels(token_type="output", team_id=team_id, model=model).inc(completion_tokens)
        COST_USD_TOTAL.labels(team_id=team_id, model=model).inc(cost_usd)

    @staticmethod
    def record_fallback(team_id: str, requested_model: str, final_model: str):
        FALLBACK_TRIGGERS_TOTAL.labels(
            team_id=team_id, requested_model=requested_model, final_model=final_model
        ).inc()

    @staticmethod
    def record_error(team_id: str, model: str, provider: str, error_type: str):
        ERRORS_TOTAL.labels(team_id=team_id, model=model, provider=provider, error_type=error_type).inc()

    @staticmethod
    def set_circuit_breaker_gauge(model: str, state_str: str):
        state_val = 0 if state_str == "CLOSED" else (1 if state_str == "HALF_OPEN" else 2)
        CIRCUIT_BREAKER_STATE.labels(model=model).set(state_val)

    @staticmethod
    def export_metrics():
        return generate_latest(), CONTENT_TYPE_LATEST

metrics_service = MetricsService()
