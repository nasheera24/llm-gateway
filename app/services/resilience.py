import os
import time
import yaml
import asyncio
import httpx
from typing import List, Dict, Any, Tuple, Optional
from app.schemas import ChatCompletionRequest, ChatCompletionResponse
from app.providers.factory import provider_factory
from app.services.circuit_breaker import circuit_breaker, CircuitState

class FallbackChainService:
    def __init__(self, config_path: str = "config/fallback_chains.yaml"):
        self.config_path = config_path
        self.tiers: Dict[str, Dict[str, Any]] = {}
        self.model_tiers: Dict[str, str] = {}
        self.load_chains()

    def load_chains(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, "r") as f:
                data = yaml.safe_load(f) or {}
                self.tiers = data.get("tiers", {})
                self.model_tiers = data.get("model_tiers", {})

    def get_fallback_chain(self, requested_model: str) -> List[str]:
        tier_id = self.model_tiers.get(requested_model, "tier_1_high")
        tier_data = self.tiers.get(tier_id, {})
        chain = tier_data.get("fallback_chain", [requested_model])

        # Ensure requested model is first in chain
        if requested_model in chain:
            chain = [requested_model] + [m for m in chain if m != requested_model]
        else:
            chain = [requested_model] + chain

        return chain

fallback_chain_service = FallbackChainService()

class ResilienceEngine:
    @staticmethod
    def is_retryable_error(status_code: Optional[int] = None, exc: Optional[Exception] = None) -> bool:
        if exc is not None:
            if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
                return True

        if status_code is not None:
            # 429 Rate Limit, 500/502/503/504 Server Errors are RETRYABLE
            if status_code in (429, 500, 502, 503, 504):
                return True
            # 401 Auth, 403 Forbidden, 400 Bad Request are NON-RETRYABLE
            if status_code in (400, 401, 403, 404):
                return False

        return False

    async def execute_with_resilience(
        self,
        request: ChatCompletionRequest,
        max_retries_per_model: int = 2
    ) -> Tuple[ChatCompletionResponse, str, List[Dict[str, Any]]]:
        """
        Executes request with exponential backoff retries, circuit breaker checks,
        and automatic fallback chain failovers.
        Returns: (ChatCompletionResponse, final_model_served, execution_logs)
        """
        chain = fallback_chain_service.get_fallback_chain(request.model)
        execution_logs = []

        for model in chain:
            # 1. Check Circuit Breaker State
            can_exec, state = circuit_breaker.can_execute(model)
            if not can_exec:
                execution_logs.append({
                    "model": model,
                    "status": "bypassed",
                    "reason": f"Circuit breaker is {state.value}. Bypassing to fallback."
                })
                continue  # Skip directly to next model in fallback chain

            # 2. Attempt call with Exponential Backoff Retries
            temp_request = request.model_copy(deep=True)
            temp_request.model = model
            provider = provider_factory.get_provider(model)

            for attempt in range(1, max_retries_per_model + 2):
                try:
                    res: ChatCompletionResponse = await provider.generate(temp_request)
                    # Success! Record success in circuit breaker and return
                    circuit_breaker.record_success(model)
                    execution_logs.append({
                        "model": model,
                        "status": "success",
                        "attempt": attempt
                    })
                    return res, model, execution_logs

                except httpx.HTTPStatusError as e:
                    status_code = e.response.status_code
                    is_retry = self.is_retryable_error(status_code=status_code)
                    
                    execution_logs.append({
                        "model": model,
                        "attempt": attempt,
                        "status": "error",
                        "status_code": status_code,
                        "is_retryable": is_retry,
                        "detail": str(e)
                    })

                    if not is_retry:
                        # Non-retryable error (e.g. 401 Auth failure) -> fail immediately!
                        circuit_breaker.record_failure(model, reason=f"Non-retryable HTTP {status_code}")
                        raise e

                    # Retryable error -> check if retries remain
                    if attempt <= max_retries_per_model:
                        delay = (2 ** (attempt - 1)) * 0.1  # 0.1s, 0.2s, 0.4s exponential backoff
                        await asyncio.sleep(delay)
                    else:
                        # Retries exhausted -> record circuit breaker failure
                        circuit_breaker.record_failure(model, reason=f"Exhausted retries on HTTP {status_code}")

                except Exception as e:
                    is_retry = self.is_retryable_error(exc=e)
                    execution_logs.append({
                        "model": model,
                        "attempt": attempt,
                        "status": "error",
                        "is_retryable": is_retry,
                        "detail": str(e)
                    })

                    if not is_retry:
                        circuit_breaker.record_failure(model, reason=f"Non-retryable exception: {str(e)}")
                        raise e

                    if attempt <= max_retries_per_model:
                        delay = (2 ** (attempt - 1)) * 0.1
                        await asyncio.sleep(delay)
                    else:
                        circuit_breaker.record_failure(model, reason=f"Exhausted retries on exception: {str(e)}")

        raise Exception(f"All providers in fallback chain exhausted for requested model '{request.model}'. Logs: {execution_logs}")

resilience_engine = ResilienceEngine()

class HealthMonitorService:
    def __init__(self):
        # Health status per model: HEALTHY, DEGRADED, DOWN
        self._health_status: Dict[str, Dict[str, Any]] = {}

    def update_status(self, model_name: str, status_str: str, latency_ms: float, is_error: bool):
        if model_name not in self._health_status:
            self._health_status[model_name] = {
                "status": "HEALTHY",
                "latencies": [],
                "errors_count": 0,
                "total_calls": 0,
                "last_check": int(time.time())
            }

        entry = self._health_status[model_name]
        entry["total_calls"] += 1
        entry["latencies"].append(latency_ms)
        if len(entry["latencies"]) > 50:
            entry["latencies"].pop(0)

        if is_error:
            entry["errors_count"] += 1

        entry["last_check"] = int(time.time())
        entry["status"] = status_str

    def get_health_report(self) -> Dict[str, Any]:
        report = {}
        for model, data in self._health_status.items():
            latencies = sorted(data["latencies"]) if data["latencies"] else [0.0]
            p99_idx = int(len(latencies) * 0.99)
            p99_latency = latencies[min(p99_idx, len(latencies) - 1)]

            report[model] = {
                "status": data["status"],
                "total_calls": data["total_calls"],
                "error_rate_percent": round((data["errors_count"] / max(data["total_calls"], 1)) * 100, 2),
                "p99_latency_ms": round(p99_latency, 2),
                "last_check": data["last_check"]
            }
        return report

health_monitor = HealthMonitorService()
