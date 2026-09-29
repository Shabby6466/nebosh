"""Consecutive-frame counters for violation debouncing, kept in Redis so they
hold across uvicorn workers and API containers (a REST-fallback client's
frames can land on a different worker each time).

One hash per session: {type, count}. A frame with the same violation type
increments count; a different type restarts at 1; a clean frame deletes it.
"""
from app.core.redis import redis_client as _redis

# Keys expire on their own if a session is never ended cleanly.
_STREAK_TTL_S = 6 * 3600

_BUMP = _redis.register_script(
    """
    local n
    if redis.call('HGET', KEYS[1], 'type') == ARGV[1] then
        n = redis.call('HINCRBY', KEYS[1], 'count', 1)
    else
        redis.call('HSET', KEYS[1], 'type', ARGV[1], 'count', 1)
        n = 1
    end
    redis.call('EXPIRE', KEYS[1], ARGV[2])
    return n
    """
)


def _key(session_id) -> str:
    return f"violation_streak:{session_id}"


async def bump(session_id, violation_type: str) -> int:
    """Record one frame showing `violation_type`; returns the current streak length."""
    return int(await _BUMP(keys=[_key(session_id)], args=[violation_type, _STREAK_TTL_S]))


async def reset(session_id) -> None:
    await _redis.delete(_key(session_id))
