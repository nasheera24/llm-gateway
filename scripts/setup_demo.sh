#!/bin/bash
set -e

echo "🚀 Starting Enterprise LLM Gateway Demo Setup..."

# Ensure Virtual Environment exists
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
fi

echo "Installing dependencies..."
./venv/bin/pip install -q -r requirements.txt

echo "🧪 Running Phase 5 Integration Test Suite..."
./venv/bin/python test_phase5_integration.py

echo "⚡ Running Phase 5 Benchmark Load Test (1,000 Requests)..."
./venv/bin/python load_test.py

echo "
======================================================
🎉 DEMO ENVIRONMENT READY!
======================================================
1. FastAPI LLM Gateway Server:
   • Endpoint: http://localhost:8080/v1/chat/completions
   • Prometheus Metrics: http://localhost:8080/metrics
   • OpenAPI Docs: http://localhost:8080/docs

2. Demo API Keys:
   • Team Alpha (Enterprise): sk-team-alpha-key-123
   • Team Beta (Free Tier):    sk-team-beta-key-456

3. Docker Compose Stack:
   To launch full containerized stack (Gateway, Redis, Prometheus, Grafana):
   $ docker-compose up -d

   • Grafana Dashboards: http://localhost:3000 (User: admin / Pass: admin)
   • Prometheus Server:  http://localhost:9091
======================================================
"
