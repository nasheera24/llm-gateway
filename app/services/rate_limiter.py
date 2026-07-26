import time
import os
import redis
from typing import Tuple, Dict, Any, Optional

# Atomic Lua Script for Token Bucket Rate Limiting in Redis
# Keys: KEYS[1] = bucket_key
# ARGV: ARGV[1] = max_tokens (capacity), ARGV[2] = refill_rate_per_sec, ARGV[3] = current_time_sec, ARGV[4] = requested_tokens, ARGV[5] = capacity_threshold_ratio
LUA_TOKEN_BUCKET_SCRIPT = """
local bucket_key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local requested = tonumber(ARGV[4])
local threshold_ratio = tonumber(ARGV[5])

local data = redis.call('HMGET', bucket_key, 'tokens', 'last_refill')
local tokens = tonumber(data[1])
local last_refill = tonumber(data[2])

if tokens == nil then
    tokens = capacity
    last_refill = now
else
    local elapsed = now - last_refill
    if elapsed > 0 then
        tokens = math.min(capacity, tokens + (elapsed * refill_rate))
        last_refill = now
    end
end

-- Calculate available threshold for priority batch requests
local effective_capacity = capacity * threshold_ratio
if tokens < (capacity - effective_capacity) or tokens < requested then
    -- Rate limit exceeded
    local tokens_needed = requested - tokens
    local retry_after = math.ceil(tokens_needed / math.max(refill_rate, 0.001))
    redis.call('HMSET', bucket_key, 'tokens', tokens, 'last_refill', last_refill)
    return {0, tostring(retry_after), tostring(math.floor(tokens))}
else
    tokens = tokens - requested
    redis.call('HMSET', bucket_key, 'tokens', tokens, 'last_refill', last_refill)
    redis.call('EXPIRE', bucket_key, 120) -- TTL 2 minutes
    return {1, "0", tostring(math.floor(tokens))}
end
"""

class RateLimiterService:
    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.redis_client = None
        self.lua_script = None
        self._in_memory_buckets: Dict[str, Dict[str, Any]] = {}
        self._init_redis()

    def _init_redis(self):
        try:
            client = redis.Redis.from_url(self.redis_url, socket_timeout=1.0, decode_responses=True)
            client.ping()
            self.redis_client = client
            self.lua_script = self.redis_client.register_script(LUA_TOKEN_BUCKET_SCRIPT)
        except Exception:
            # Fall back to in-memory rate limiting if Redis is not running locally
            self.redis_client = None

    def check_rate_limit(
        self,
        team_id: str,
        limit_rpm: int = 60,
        priority: str = "high",
        requested_tokens: int = 1
    ) -> Tuple[bool, int, int]:
        """
        Checks rate limit for a team.
        Returns: (allowed: bool, retry_after_sec: int, remaining_tokens: int)
        """
        now = time.time()
        capacity = float(limit_rpm)
        refill_rate = capacity / 60.0  # refill tokens per second

        # Threshold ratio: High priority gets 100% capacity (1.0), Batch priority gets 75% capacity (0.75)
        threshold_ratio = 1.0 if priority == "high" else 0.75
        bucket_key = f"rate_limit:{team_id}:rpm"

        if self.redis_client and self.lua_script:
            try:
                res = self.lua_script(
                    keys=[bucket_key],
                    args=[capacity, refill_rate, now, requested_tokens, threshold_ratio]
                )
                allowed = bool(res[0] == 1)
                retry_after = int(res[1])
                remaining = int(res[2])
                return allowed, retry_after, remaining
            except Exception:
                pass  # Fallback to in-memory bucket on Redis network error

        # In-Memory Token Bucket Fallback Implementation
        bucket = self._in_memory_buckets.get(bucket_key, {"tokens": capacity, "last_refill": now})
        elapsed = now - bucket["last_refill"]
        bucket["tokens"] = min(capacity, bucket["tokens"] + (elapsed * refill_rate))
        bucket["last_refill"] = now

        effective_limit = capacity * threshold_ratio
        if bucket["tokens"] < (capacity - effective_limit) or bucket["tokens"] < requested_tokens:
            tokens_needed = requested_tokens - bucket["tokens"]
            retry_after = int(tokens_needed / max(refill_rate, 0.001)) + 1
            self._in_memory_buckets[bucket_key] = bucket
            return False, retry_after, int(bucket["tokens"])

        bucket["tokens"] -= requested_tokens
        self._in_memory_buckets[bucket_key] = bucket
        return True, 0, int(bucket["tokens"])

rate_limiter = RateLimiterService()
