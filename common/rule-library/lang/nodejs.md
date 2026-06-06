# Language: Node.js

## Project Structure

```
src/
  routes/        # Route definitions (thin — delegate to services)
  services/      # Business logic
  middleware/    # Auth, validation, error handling, rate limiting
  models/        # Data models / schemas
  utils/         # Pure helpers
  config/        # Environment loading, app config
```

## API Design

- RESTful conventions (HTTP methods, status codes)
- Consistent error response format: `{ error: string, code: string }`
- Request validation middleware (zod, joi, or class-validator)
- Versioning strategy (URL prefix: `/api/v1/`)

## Repository Pattern

```typescript
interface Repository<T> {
  findAll(filters?: Filters): Promise<T[]>
  findById(id: string): Promise<T | null>
  create(data: CreateDto): Promise<T>
  update(id: string, data: UpdateDto): Promise<T>
  delete(id: string): Promise<void>
}
```

## Environment & Config

- Validate all env vars at startup (fail fast on missing config)
- Use zod or envalid for schema validation
- Never access `process.env` directly outside config module
- Separate config per environment (dev, test, prod)

## Graceful Shutdown

```typescript
async function shutdown(signal: string) {
  logger.info(`${signal} received, shutting down`)
  server.close()
  await db.disconnect()
  process.exit(0)
}
process.on('SIGTERM', () => shutdown('SIGTERM'))
process.on('SIGINT', () => shutdown('SIGINT'))
```

## Async Patterns

- async/await over callbacks
- `Promise.all` for parallel operations
- Graceful error handling with try/catch
- `AbortController` for cancellation

## Logging

- Structured JSON logging (pino, winston)
- Log levels: error, warn, info, debug
- Include request ID in all log entries
- Never log sensitive data (passwords, tokens, PII)

## Security

- Environment variables for config
- No secrets in code
- Input sanitization
- Rate limiting on endpoints
- Helmet for HTTP headers

## Error Handling

- Centralized error handler middleware
- Operational vs programmer errors
- Structured error responses
- No stack traces in production

## Testing

- Jest or Vitest
- Supertest for HTTP assertions
- Mock external services
- In-memory database for integration tests
