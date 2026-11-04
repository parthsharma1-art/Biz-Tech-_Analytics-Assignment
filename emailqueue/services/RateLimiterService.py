import time
import uuid
import logging
from typing import Tuple, Optional
import redis

from emailqueue.config.RedisConfig import RedisConfig

logger = logging.getLogger(__name__)

# Atomic sliding window rate limiter Lua script
SLIDING_WINDOW_LUA_SCRIPT = """
local rateLimitKey = KEYS[1]
local currentTime = tonumber(ARGV[1])
local windowSeconds = tonumber(ARGV[2])
local maxLimit = tonumber(ARGV[3])
local memberId = ARGV[4]

local windowStart = currentTime - windowSeconds

-- Prune requests outside the current sliding window
redis.call('ZREMRANGEBYSCORE', rateLimitKey, '-inf', windowStart)

-- Count remaining events in current window
local currentCount = redis.call('ZCARD', rateLimitKey)

if currentCount < maxLimit then
    -- Add the new request timestamp
    redis.call('ZADD', rateLimitKey, currentTime, memberId)
    redis.call('EXPIRE', rateLimitKey, math.ceil(windowSeconds) + 15)
    return {1, 0, maxLimit - currentCount - 1}
else
    -- Find the oldest timestamp in the current window to determine retry cooldown
    local oldestEntries = redis.call('ZRANGE', rateLimitKey, 0, 0, 'WITHSCORES')
    local retryAfter = 1
    if #oldestEntries > 1 then
        local oldestTimestamp = tonumber(oldestEntries[2])
        local waitTime = (oldestTimestamp + windowSeconds) - currentTime
        if waitTime > 0 then
            retryAfter = math.ceil(waitTime)
        end
    end
    return {0, retryAfter, 0}
end
"""

class RateLimiterService:
    DEFAULT_RATE_LIMIT_KEY = "rate_limit:email_global_window"
    MAX_EMAILS_PER_MINUTE = 200
    WINDOW_SECONDS = 60

    def __init__(
        self,
        redisConfig: Optional[RedisConfig] = None,
        maxLimit: int = MAX_EMAILS_PER_MINUTE,
        windowSeconds: int = WINDOW_SECONDS,
        rateLimitKey: str = DEFAULT_RATE_LIMIT_KEY
    ):
        self.redisConfig = redisConfig or RedisConfig.getInstance()
        self.maxLimit = maxLimit
        self.windowSeconds = windowSeconds
        self.rateLimitKey = rateLimitKey
        self._scriptSha: Optional[str] = None

    def getRedisClient(self) -> redis.Redis:
        return self.redisConfig.getClient()

    def acquirePermission(self) -> Tuple[bool, int]:
        """
        Atomically checks and consumes a token from the sliding window.
        Returns:
            Tuple[bool, int]: (allowed, retryAfterSeconds)
            - If allowed is True, permission is granted (retryAfterSeconds = 0).
            - If allowed is False, rate limit is hit (retryAfterSeconds is backoff duration).
        """
        redisClient = self.getRedisClient()
        currentTime = time.time()
        memberId = f"{currentTime}:{uuid.uuid4().hex}"

        try:
            # Execute Lua script atomically on Redis server
            evalResult = redisClient.eval(
                SLIDING_WINDOW_LUA_SCRIPT,
                1,
                self.rateLimitKey,
                currentTime,
                self.windowSeconds,
                self.maxLimit,
                memberId
            )
            # eval returns [allowedFlag, retryAfter, remaining]
            allowed = bool(evalResult[0] == 1)
            retryAfterSeconds = int(evalResult[1])
            return allowed, retryAfterSeconds
        except (redis.ConnectionError, redis.TimeoutError) as redisError:
            logger.error(
                "Redis is unavailable during rate limit check: %s. Enforcing fail-safe wait.",
                str(redisError)
            )
            # Fail-safe: When Redis is unreachable, do not overload downstream provider;
            # request a 5-second backoff.
            return False, 5

    def reset(self) -> None:
        """Clears the sliding window rate limiter key (used for testing and maintenance)."""
        try:
            self.getRedisClient().delete(self.rateLimitKey)
        except Exception as error:
            logger.warning("Error clearing rate limit key: %s", str(error))

    def getCurrentCount(self) -> int:
        """Returns the number of requests currently in the sliding window."""
        try:
            currentTime = time.time()
            windowStart = currentTime - self.windowSeconds
            redisClient = self.getRedisClient()
            redisClient.zremrangebyscore(self.rateLimitKey, "-inf", windowStart)
            return int(redisClient.zcard(self.rateLimitKey))
        except Exception:
            return 0

