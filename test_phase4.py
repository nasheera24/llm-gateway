import os
import json
import asyncio
import httpx
from app.main import app
from app.services.alerting import alerting_service

ALPHA_KEY = "sk-team-alpha-key-123"

async def test_prometheus_metrics_endpoint():
    print("\n1. Testing Prometheus Exporter Endpoint (/metrics)...")
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Make a standard request to generate metrics
        headers = {"Authorization": f"Bearer {ALPHA_KEY}"}
        payload = {"model": "gpt-4o", "messages": [{"role": "user", "content": "Prometheus test"}]}
        req_res = await client.post("/v1/chat/completions", headers=headers, json=payload)
        assert req_res.status_code == 200

        # Fetch Prometheus metrics text output
        metrics_res = await client.get("/metrics")
        print(f"Metrics Status Code: {metrics_res.status_code}")
        metrics_text = metrics_res.text

        # Verify key Prometheus metrics exist in output
        assert "llm_gateway_requests_total" in metrics_text
        assert "llm_gateway_tokens_total" in metrics_text
        assert "llm_gateway_cost_usd_total" in metrics_text
        assert "llm_gateway_latency_seconds_bucket" in metrics_text

        print("Prometheus Metrics Sample Output:")
        lines = [line for line in metrics_text.splitlines() if line.startswith("llm_gateway_")]
        for line in lines[:6]:
            print(f"  {line}")

async def test_slack_alerting_events():
    print("\n2. Testing Slack Webhook Alerting Service...")
    await alerting_service.send_slack_alert("TEST_ALERT_EVENT", {
        "team_id": "team_alpha",
        "reason": "Observability integration test",
        "severity": "HIGH"
    })

    history = alerting_service.get_alert_history()
    print(f"Alert History Count: {len(history)}")
    latest_alert = history[-1]
    print(f"Latest Alert Event: {latest_alert['event_type']}")
    print(f"Alert Details: {latest_alert['details']}")

    assert latest_alert["event_type"] == "TEST_ALERT_EVENT"
    assert latest_alert["details"]["team_id"] == "team_alpha"

async def test_grafana_dashboards_existence():
    print("\n3. Testing Grafana Dashboard Configurations...")
    dashboards = [
        "grafana/dashboards/operations.json",
        "grafana/dashboards/business.json",
        "grafana/dashboards/performance.json"
    ]

    for path in dashboards:
        assert os.path.exists(path)
        with open(path, "r") as f:
            data = json.load(f)
            print(f" Dashboard Loaded: {data['title']} ({len(data['panels'])} panels)")

async def main():
    await test_prometheus_metrics_endpoint()
    await test_slack_alerting_events()
    await test_grafana_dashboards_existence()

if __name__ == "__main__":
    asyncio.run(main())
