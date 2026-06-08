class RateLimiter:
    """Fixed-window rate limiter: allow at most `limit` calls per `window`
    seconds. The window starts at the first call and resets once `window`
    seconds have elapsed. Time is injected via `now` (seconds) for testability.

    allow(now) returns True if the call is permitted, else False.
    """

    def __init__(self, limit, window):
        self.limit = limit
        self.window = window
        self.count = 0
        self.start = None

    def allow(self, now):
        if self.start is None:
            self.start = now
        if now - self.start >= self.window:
            self.count = 0
        self.count += 1
        return self.count <= self.limit
