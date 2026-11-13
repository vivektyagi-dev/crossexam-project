"""Shared AI rate limit: one Redis token bucket for ALL workers.

Adding workers past the provider's requests-per-minute limit only produces
"too many requests" errors, so every model call takes a token first.
"""

from __future__ import annotations

import time

import redis

from app.config import settings

_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_per_ms = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local state = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(state[1]) or capacity
local ts = tonumber(state[2]) or now
tokens = math.min(capacity, tokens + (now - ts) * refill_per_ms)
local allowed = 0
local wait = 0
if tokens >= 1 then
  tokens = tokens - 1
  allowed = 1
else
  wait = math.ceil((1 - tokens) / refill_per_ms)
end
redis.call('HSET', key, 'tokens', tokens, 'ts', now)
redis.call('PEXPIRE', key, 120000)
return {allowed, wait}
"""

_client: redis.Redis | None = None
_script = None


def _redis() -> redis.Redis:
    global _client, _script
    if _client is None:
        _client = redis.Redis.from_url(settings.redis_url)
        _script = _client.register_script(_LUA)
    return _client


def acquire(bucket: str = "llm", rpm: int | None = None, timeout_s: float = 120.0) -> float:
    """Block until a token is available. Returns seconds waited."""
    rpm = rpm or settings.llm_requests_per_minute
    _redis()
    capacity = max(1, rpm // 6)  # allow short bursts of ~10s worth of calls
    refill_per_ms = rpm / 60000.0
    started = time.monotonic()
    while True:
        allowed, wait_ms = _script(keys=[f"ratelimit:{bucket}"],
                                   args=[capacity, refill_per_ms, int(time.time() * 1000)])
        if int(allowed) == 1:
            return time.monotonic() - started
        if time.monotonic() - started > timeout_s:
            raise TimeoutError("Timed out waiting for the shared LLM rate limit")
        time.sleep(min(int(wait_ms), 2000) / 1000.0)
