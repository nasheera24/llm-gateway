import time
import asyncio
import httpx
from app.main import app

ALPHA_KEY = "sk-team-alpha-key-123"
BETA_KEY = "sk-team-beta-key-456"

async def run_load_test(total_requests: int = 1000, batch_size: int = 100):
    print(f"\n⚡ Starting High-Concurrency Load Test: {total_requests} Requests (Batch Size: {batch_size})...")
    transport = httpx.ASGITransport(app=app)

    latencies = []
    status_counts = {}
    start_test_time = time.time()

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for b in range(0, total_requests, batch_size):
            tasks = []
            for i in range(batch_size):
                key = ALPHA_KEY if i % 2 == 0 else BETA_KEY
                model = "gpt-4o" if i % 3 == 0 else ("gpt-4o-mini" if i % 3 == 1 else "claude-3-5-sonnet-20240620")
                priority = "high" if i % 4 != 0 else "batch"
                headers = {"Authorization": f"Bearer {key}", "X-Priority": priority}
                payload = {"model": model, "messages": [{"role": "user", "content": f"Load test request #{b+i}"}]}

                t0 = time.time()
                tasks.append(client.post("/v1/chat/completions", headers=headers, json=payload))

            results = await asyncio.gather(*tasks, return_exceptions=True)
            t_end = time.time()

            for res in results:
                if isinstance(res, httpx.Response):
                    code = res.status_code
                    status_counts[code] = status_counts.get(code, 0) + 1
                    if code == 200 and "gateway_metadata" in res.json():
                        latencies.append(res.json()["gateway_metadata"]["latency_ms"])
                else:
                    status_counts["exception"] = status_counts.get("exception", 0) + 1

    total_duration = time.time() - start_test_time
    rps = round(total_requests / total_duration, 2)

    latencies.sort()
    p50 = latencies[int(len(latencies) * 0.50)] if latencies else 0
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0
    p99 = latencies[int(len(latencies) * 0.99)] if latencies else 0

    print("\n📊 Load Test Benchmark Results:")
    print(f"  • Total Duration: {total_duration:.2f} seconds")
    print(f"  • Throughput: {rps} Requests/sec")
    print(f"  • Status Code Distribution: {status_counts}")
    print(f"  • Gateway Overhead Latency P50: {p50:.2f} ms")
    print(f"  • Gateway Overhead Latency P95: {p95:.2f} ms")
    print(f"  • Gateway Overhead Latency P99: {p99:.2f} ms")

if __name__ == "__main__":
    asyncio.run(run_load_test(total_requests=1000, batch_size=100))
