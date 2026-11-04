import concurrent.futures
from unittest.mock import patch
import redis
import pytest

from emailqueue.services.RateLimiterService import RateLimiterService

class TestRateLimiterService:
    def testAllowUnderLimit(self, rateLimiterService: RateLimiterService):
        """Verifies requests under 200/minute are granted permission immediately."""
        for _ in range(50):
            allowed, retryAfter = rateLimiterService.acquirePermission()
            assert allowed is True
            assert retryAfter == 0

    def testStrictlyBlockExceedingLimit(self, rateLimiterService: RateLimiterService):
        """Verifies that the 201st request in a 60-second window is rejected."""
        # Acquire up to the max limit (200)
        for i in range(200):
            allowed, retryAfter = rateLimiterService.acquirePermission()
            assert allowed is True, f"Request {i+1} should have been allowed"
            assert retryAfter == 0

        # The 201st request must be denied
        deniedAllowed, deniedRetryAfter = rateLimiterService.acquirePermission()
        assert deniedAllowed is False
        assert deniedRetryAfter > 0

    def testConcurrentWorkersShareSameLimit(self, rateLimiterService: RateLimiterService):
        """
        Simulates multiple Celery workers concurrently acquiring tokens.
        Asserts that the shared atomic Redis limit never allows > 200 permissions.
        """
        totalAttempts = 300
        allowedCount = 0
        deniedCount = 0

        def workerAttempt(_):
            return rateLimiterService.acquirePermission()

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(workerAttempt, range(totalAttempts)))

        for allowed, retryAfter in results:
            if allowed:
                allowedCount += 1
            else:
                deniedCount += 1
                assert retryAfter > 0

        assert allowedCount == 200, f"Expected exactly 200 allowed, got {allowedCount}"
        assert deniedCount == 100, f"Expected exactly 100 denied, got {deniedCount}"

    def testRedisUnavailableFailSafe(self, rateLimiterService: RateLimiterService):
        """
        Verifies behavior when Redis becomes unavailable:
        The limiter safely fails closed/defers with backoff rather than crashing or exceeding limit.
        """
        with patch.object(rateLimiterService, "getRedisClient") as mockClientGetter:
            mockClient = mockClientGetter.return_value
            mockClient.eval.side_effect = redis.ConnectionError("Connection refused to Redis cluster")

            allowed, retryAfter = rateLimiterService.acquirePermission()
            assert allowed is False
            assert retryAfter == 5

