# Language: Go

## Project Structure

```
cmd/               # Application entry points (one main per binary)
internal/          # Private code (enforced by Go toolchain)
pkg/               # Public library code
api/               # API definitions (protobuf, OpenAPI)
```

- Use `internal/` to prevent external imports
- Keep `cmd/` thin — delegate to packages in `internal/`

## Modules & Dependencies

- `go.mod` defines module path and dependencies
- Run `go mod tidy` after dependency changes
- Vendor with `go mod vendor` for reproducible builds (optional)

## Naming Conventions

- **MixedCaps** for exported, **mixedCaps** for unexported (no snake_case)
- Short variable names: `i`, `r`, `w`, `ctx`, `err`
- Receiver names: 1-2 letters, consistent (`c *Client`)
- Package names: lowercase, single word, no underscores
- Interfaces: single-method end in `-er` (`Reader`, `Writer`, `Closer`)
- Acronyms: all caps (`URL`, `HTTP`, `ID`)

## Interfaces

- Accept interfaces, return structs
- Keep interfaces small (1-3 methods)
- Define interfaces where they're consumed, not where implemented
- Compose with embedding: `ReadCloser` = `Reader` + `Closer`

## Error Handling

- Check errors immediately — never ignore
- Wrap with context: `fmt.Errorf("connect to %s: %w", addr, err)`
- Use `errors.Is()` for sentinel errors, `errors.As()` for typed errors
- Return errors, don't panic (reserve panic for truly unrecoverable)
- Custom errors: implement `error` interface or use sentinel `var ErrNotFound = errors.New(...)`

```go
result, err := doWork()
if err != nil {
    return fmt.Errorf("doWork failed: %w", err)
}
```

## Concurrency

- Pass `context.Context` as first parameter for cancellation/timeout
- Communicate via channels: `ch := make(chan T, bufSize)`
- Use `sync.WaitGroup` to wait for goroutine completion
- Always provide goroutine exit paths — prevent leaks
- Use `sync.Mutex` for shared state; prefer channels for coordination
- Worker pool pattern for bounded concurrency

```go
g, ctx := errgroup.WithContext(ctx)
for _, item := range items {
    g.Go(func() error { return process(ctx, item) })
}
if err := g.Wait(); err != nil { return err }
```

## Testing

- Test files: `*_test.go` in same package (or `_test` package for black-box)
- Table-driven tests with `t.Run()` for subtests
- Call `t.Parallel()` for parallelizable tests
- Race detection: `go test -race ./...`
- Coverage: `go test -cover ./...`
- Benchmarks: `func BenchmarkX(b *testing.B)`

```go
tests := []struct{ name string; input int; want int }{
    {"zero", 0, 0},
    {"positive", 5, 25},
}
for _, tt := range tests {
    t.Run(tt.name, func(t *testing.T) {
        if got := Square(tt.input); got != tt.want {
            t.Errorf("Square(%d) = %d, want %d", tt.input, got, tt.want)
        }
    })
}
```

## Linting & Formatting

- `gofmt` or `goimports` before every commit (auto-format)
- `golangci-lint run` for comprehensive linting
- Configure `.golangci.yml` for project-specific rules
