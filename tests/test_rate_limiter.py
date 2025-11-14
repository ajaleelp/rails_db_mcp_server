import time

import pytest

from rails_mcp_server.rate_limiter import RateLimiter, RateLimitExceeded


def test_rate_limiter_rejects_excess_requests() -> None:
    limiter = RateLimiter(requests_per_minute=2)
    limiter.check_and_record()
    limiter.check_and_record()
    with pytest.raises(RateLimitExceeded):
        limiter.check_and_record()


def test_rate_limiter_allows_after_window() -> None:
    limiter = RateLimiter(requests_per_minute=1)
    limiter.WINDOW_SECONDS = 0.1
    limiter.check_and_record()
    time.sleep(0.2)
    limiter.check_and_record()  # Should not raise
