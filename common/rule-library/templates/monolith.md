# Template: Monolith Services

## Module Organization

```
modules/
  users/       -> User domain (routes, services, models)
  orders/      -> Order domain
  shared/      -> Cross-cutting (auth, logging, utils)
```

## Dependencies

- Modules depend on shared, not each other
- If modules need to communicate, use events or shared service
- No circular dependencies

## Database

- Schema per module (or clear table ownership)
- Migrations versioned with code
- Shared tables owned by one module
