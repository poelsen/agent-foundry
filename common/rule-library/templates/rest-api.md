# Template: REST API Backend

REST API backend service development. Covers endpoint organization, layered architecture, reliability, and observability.

## Endpoint Organization

- Group by resource/domain, not by HTTP method
- Version in URL path (`/v1/`) or header
- Consistent naming: plural nouns for collections

## Layers

```
routes/        -> HTTP handling, validation
services/      -> Business logic
repositories/  -> Data access
```

## Error Handling

- Centralized error middleware
- Consistent error response format
- Operational vs programmer errors

## Middleware Chain

- Auth -> Rate limit -> Validation -> Handler -> Error handler
- Each middleware single-purpose

## Reliability

- Retry with exponential backoff + jitter
- Circuit breakers for external dependencies
- Timeouts on all external calls
- Idempotent operations where possible

## Observability

- Structured logging with correlation IDs
- Log actionable events, not noise
- Health checks and readiness probes
- Never log secrets or PII

## Data Handling

- Validate all external input (schema validation)
- Strong types at API boundaries
- Graceful degradation over hard failures

## Concurrency

- Document thread-safety assumptions
- Bulkhead isolation for resource pools

## Checklist

- [ ] Endpoints grouped by resource
- [ ] Error format consistent across all endpoints
- [ ] Retries have backoff and limits
- [ ] External calls have timeouts
- [ ] Errors logged with correlation ID
- [ ] Input validated at API boundary
- [ ] Health check endpoint exists
