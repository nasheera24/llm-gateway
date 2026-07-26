import asyncio
import time
import json
import httpx
from app.main import app

from app.services.circuit_breaker import circuit_breaker, CircuitState
from app.services.resilience import fallback_chain_service

ALPHA_KEY = "sk-team-alpha-key-123"

async def test_fallback_chain_resolution():
    print("\n1. Testing Tier-Based Fallback Chain Resolution...")
    chain_gpt4 = fallback_chain_service.get_fallback_chain("gpt-4o")
    print(f"Fallback Chain for 'gpt-4o': {chain_gpt4}")
    assert chain_gpt4 == ["gpt-4o", "claude-3-5-sonnet-20240620", "ollama/llama3.1"]

    chain_mini = fallback_chain_service.get_fallback_chain("gpt-4o-mini")
    print(f"Fallback Chain for 'gpt-4o-mini': {chain_mini}")
    assert chain_mini == ["gpt-4o-mini", "ollama/llama3.1"]

async def test_circuit_breaker_state_machine():
    print("\n2. Testing Circuit Breaker State Transitions (CLOSED -> OPEN -> HALF_OPEN -> CLOSED)...")
    model_test = "test-failing-model"

    # 1. Initial State: CLOSED
    can_exec, state = circuit_breaker.can_execute(model_test)
    print(f"Initial State: {state.value} | Can Execute: {can_exec}")
    assert state == CircuitState.CLOSED and can_exec is True

    # 2. Record 3 failures to trip circuit open
    circuit_breaker.record_failure(model_test, reason="Simulated Timeout 1")
    circuit_breaker.record_failure(model_test, reason="Simulated Timeout 2")
    circuit_breaker.record_failure(model_test, reason="Simulated Timeout 3")

    can_exec, state = circuit_breaker.can_execute(model_test)
    print(f"After 3 Failures: {state.value} | Can Execute: {can_exec}")
    assert state == CircuitState.OPEN and can_exec is False

    # 3. Fast-forward time to test HALF_OPEN transition
    circuit_breaker._breakers[model_test]["opened_at"] = time.time() - 15.0 # simulate 15s elapsed
    can_exec, state = circuit_breaker.can_execute(model_test)
    print(f"After Cooldown: {state.value} | Can Execute: {can_exec}")
    assert state == CircuitState.HALF_OPEN and can_exec is True

    # 4. Record probe success to recover to CLOSED
    circuit_breaker.record_success(model_test)
    can_exec, state = circuit_breaker.can_execute(model_test)
    print(f"After Probe Success: {state.value} | Can Execute: {can_exec}")
    assert state == CircuitState.CLOSED and can_exec is True

async def test_automatic_failover_execution():
    print("\n3. Testing Automatic Failover Execution...")
    transport = httpx.ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {ALPHA_KEY}"}
    payload = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "Failover integration test"}]
    }

    # Simulate OpenAI model in OPEN circuit breaker state to force failover to Anthropic Claude
    circuit_breaker.record_failure("gpt-4o", "Simulated outage")
    circuit_breaker.record_failure("gpt-4o", "Simulated outage")
    circuit_breaker.record_failure("gpt-4o", "Simulated outage")

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/v1/chat/completions", headers=headers, json=payload)
        print(f"Status Code: {res.status_code}")
        data = res.json()
        meta = data.get("gateway_metadata", {})
        print(f"Requested Model: {meta.get('requested_model')}")
        print(f"Final Model Served: {meta.get('final_model_served')}")
        print(f"Fallback Triggered: {meta.get('fallback_triggered')}")
        print(f"Resilience Logs:\n{json.dumps(meta.get('resilience_logs'), indent=2)}")

        assert meta.get('fallback_triggered') is True
        assert meta.get('final_model_served') == "claude-3-5-sonnet-20240620"

    # Recover circuit breaker for gpt-4o
    circuit_breaker.record_success("gpt-4o")

async def test_admin_health_and_breakers_api():
    print("\n4. Testing Admin Health & Circuit Breaker Endpoints...")
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res_health = await client.get("/v1/admin/health")
        print(f"Health Report Status: {res_health.status_code}")
        print(f"Health Data: {res_health.json()}")

        res_breakers = await client.get("/v1/admin/circuit-breakers")
        print(f"Circuit Breakers Status: {res_breakers.status_code}")
        print(f"Breakers Data: {res_breakers.json()['breakers']}")

async def main():
    await test_fallback_chain_resolution()
    await test_circuit_breaker_state_machine()
    await test_automatic_failover_execution()
    await test_admin_health_and_breakers_api()

if __name__ == "__main__":
    asyncio.run(main())
