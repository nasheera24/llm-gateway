import asyncio
import httpx
import json
from app.main import app

ALPHA_KEY = "sk-team-alpha-key-123"
BETA_KEY = "sk-team-beta-key-456"

async def test_rate_limiting_and_retry_after():
    print("\n1. Testing Token-Bucket Rate Limiting & 429 Retry-After Headers...")
    transport = httpx.ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {BETA_KEY}"} # Beta team RPM limit = 20
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "Rate limit test"}]
    }

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Exhaust rate limit by sending requests
        for i in range(25):
            res = await client.post("/v1/chat/completions", headers=headers, json=payload)
            if res.status_code == 429:
                print(f" Request #{i+1} Blocked! Status: 429")
                print(f" Retry-After Header: {res.headers.get('Retry-After')} seconds")
                print(f" Error Detail: {res.json()['detail']}")
                break
            else:
                print(f" Request #{i+1} Allowed (200 OK) | Remaining Tokens: {res.headers.get('X-RateLimit-Remaining')}")

async def test_priority_tiering():
    print("\n2. Testing Priority Tiering (High vs Batch)...")
    transport = httpx.ASGITransport(app=app)
    headers_batch = {"Authorization": f"Bearer {ALPHA_KEY}", "X-Priority": "batch"}
    payload = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "Priority test"}]
    }

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/v1/chat/completions", headers=headers_batch, json=payload)
        print(f"Batch Request Status: {res.status_code}")
        if res.status_code == 200:
            print(f"Priority metadata: {res.json()['gateway_metadata']['priority_level']}")

async def test_budget_cap_enforcement():
    print("\n3. Testing Cost Calculation & Budget Cap Enforcement...")
    transport = httpx.ASGITransport(app=app)
    
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Update team_beta budget to $0.0001 (very small) via Admin API to trigger cap
        admin_headers = {"X-Admin-User": "admin@company.com"}
        update_res = await client.put(
            "/v1/admin/teams/team_beta/limits",
            headers=admin_headers,
            json={"monthly_budget_usd": 0.0001}
        )
        print(f"Admin Budget Cap Set To: ${update_res.json()['updated_fields']['monthly_budget_usd']}")

        # 2. Make first call to accumulate spend
        headers = {"Authorization": f"Bearer {BETA_KEY}"}
        payload = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "Cost tracking test"}]}
        res1 = await client.post("/v1/chat/completions", headers=headers, json=payload)
        print(f"Call 1 Status: {res1.status_code}")

        # 3. Next call should be BLOCKED due to budget cap exceeded
        res2 = await client.post("/v1/chat/completions", headers=headers, json=payload)
        print(f"Call 2 Status: {res2.status_code} (Expected 429 Budget Exceeded)")
        print(f"Blocked Reason: {res2.json()['detail']}")

        # Reset team_beta budget back to normal
        await client.put(
            "/v1/admin/teams/team_beta/limits",
            headers=admin_headers,
            json={"monthly_budget_usd": 50.0}
        )

async def test_admin_api_and_audit_logs():
    print("\n4. Testing Admin API Endpoints & Audit Logging...")
    transport = httpx.ASGITransport(app=app)
    admin_headers = {"X-Admin-User": "security_lead"}

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. View team limits
        res1 = await client.get("/v1/admin/teams/team_alpha/limits")
        print(f"Team Alpha Limits: RPM = {res1.json()['rate_limit_rpm']}, Budget = ${res1.json()['monthly_budget_usd']}")

        # 2. Update RPM dynamically
        res2 = await client.put(
            "/v1/admin/teams/team_alpha/limits",
            headers=admin_headers,
            json={"rate_limit_rpm": 120}
        )
        print(f"Dynamic Limit Update: {res2.json()['message']}")

        # 3. View Spending Dashboard
        res3 = await client.get("/v1/admin/spending")
        print("Spending Dashboard Summary:")
        for t in res3.json()["teams_spending"]:
            print(f"  Team: {t['team_name']} | Budget: ${t['monthly_budget_usd']} | Spend: ${t['current_spend_usd']}")

        # 4. View Audit Logs
        res4 = await client.get("/v1/admin/audit-logs")
        print("\nAudit Log History:")
        for log in res4.json()["audit_logs"]:
            print(f"  [{log['actor']}] Changed {log['field_changed']} on '{log['team_id']}' from {log['old_value']} to {log['new_value']}")

async def main():
    await test_rate_limiting_and_retry_after()
    await test_priority_tiering()
    await test_budget_cap_enforcement()
    await test_admin_api_and_audit_logs()

if __name__ == "__main__":
    asyncio.run(main())
