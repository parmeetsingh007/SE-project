"""The shared rate limiter itself: real timing, no mocked sleep.

Kept separate from test_llm_client_retry.py, whose autouse fixture patches
time.sleep to keep those tests fast — that would defeat this file's purpose.
"""

import time

from src.agents.llm_client import _RateLimiter


def test_allows_calls_up_to_the_limit_without_waiting() -> None:
    limiter = _RateLimiter(limit=3, window_seconds=5.0)

    start = time.monotonic()
    limiter.acquire()
    limiter.acquire()
    limiter.acquire()
    elapsed = time.monotonic() - start

    assert elapsed < 0.1


def test_blocks_until_the_window_frees_a_slot() -> None:
    limiter = _RateLimiter(limit=2, window_seconds=0.2)

    start = time.monotonic()
    limiter.acquire()
    limiter.acquire()
    limiter.acquire()  # third call within the window must wait it out
    elapsed = time.monotonic() - start

    assert elapsed >= 0.15  # allow a little scheduling slack


def test_old_calls_age_out_of_the_window() -> None:
    limiter = _RateLimiter(limit=1, window_seconds=0.1)

    limiter.acquire()
    time.sleep(0.15)  # past the window, so the next call shouldn't block

    start = time.monotonic()
    limiter.acquire()
    elapsed = time.monotonic() - start

    assert elapsed < 0.05
