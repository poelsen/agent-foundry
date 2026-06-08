from limiter import RateLimiter


def test_allows_under_limit():
    rl = RateLimiter(limit=2, window=10)
    assert rl.allow(0) is True
    assert rl.allow(1) is True


def test_blocks_over_limit_in_window():
    rl = RateLimiter(limit=2, window=10)
    rl.allow(0)
    rl.allow(1)
    assert rl.allow(5) is False


def test_new_window_resets_and_re_limits():
    rl = RateLimiter(limit=2, window=10)
    rl.allow(0)
    rl.allow(1)
    assert rl.allow(5) is False        # still in first window
    assert rl.allow(11) is True        # window rolled over -> allowed again
    assert rl.allow(12) is True        # second call in the new window
    assert rl.allow(13) is False       # limit reached again in the new window
