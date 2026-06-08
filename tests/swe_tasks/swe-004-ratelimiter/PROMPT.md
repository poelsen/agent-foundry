`RateLimiter` stops enforcing the limit after the first window expires. Once
`window` seconds have passed, it lets through *every* subsequent call instead
of starting a fresh window that re-applies the limit. A limiter set to 2 calls
per 10s correctly blocks the 3rd call early on, but after t=10 it allows
unlimited calls. Each new window should reset the count *and* re-apply the
limit within that window.
