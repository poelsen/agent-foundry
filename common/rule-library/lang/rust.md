# Language: Rust

## Tooling

- Target latest stable edition (2021+)
- `cargo build --release` for optimized builds
- `cargo clippy --all-targets -- -D warnings` for linting
- `cargo fmt` for formatting (run before commit)
- `cargo test --all-features` for tests

## Project Structure

```
src/
  lib.rs           # Library root
  main.rs          # Binary entry point
  bin/             # Additional binaries
tests/             # Integration tests
benches/           # Benchmarks
```

- Unit tests in same file with `#[cfg(test)]` module
- Use `mod` for organizing into submodules
- Workspace (`Cargo.toml` with `[workspace]`) for multi-crate projects

## Ownership & Borrowing

- Prefer borrowing (`&T`, `&mut T`) over cloning — pass ownership only when needed
- Clone when multiple owners needed or crossing thread boundaries
- Let compiler infer lifetimes — annotate only when required
- Use `Cow<'_, str>` when ownership is conditionally needed

## Error Handling

- `Result<T, E>` for recoverable errors, `Option<T>` for missing values
- Propagate with `?` operator
- Libraries: define error types with `thiserror`
- Applications: use `anyhow` for ergonomic error handling
- Never `unwrap()` or `expect()` in production code paths

```rust
fn read_config(path: &Path) -> Result<Config, AppError> {
    let content = fs::read_to_string(path)
        .context("failed to read config file")?;
    let config: Config = toml::from_str(&content)
        .context("failed to parse config")?;
    Ok(config)
}
```

## Types & Traits

- Generics (`impl Trait`, `<T: Trait>`) for compile-time dispatch (zero-cost)
- Trait objects (`Box<dyn Trait>`) for runtime polymorphism
- Derive common traits: `Debug`, `Clone`, `PartialEq`, `Eq`, `Hash`
- Implement `Display` for user-facing types
- Use newtypes for type safety: `struct UserId(u64)`

## Concurrency

- `Send`/`Sync` marker traits enforce thread safety at compile time
- `tokio` for async I/O workloads
- `rayon` for CPU-bound parallel computation
- Shared state: `Arc<Mutex<T>>` (or `RwLock` for read-heavy)
- Prefer message passing (`mpsc`, `crossbeam`) over shared state
- Never block in async contexts — use `tokio::task::spawn_blocking`

## Naming

- `snake_case` — functions, variables, modules, files
- `CamelCase` — types, traits, enums
- `SCREAMING_SNAKE_CASE` — constants, statics

## Unsafe Code

- Avoid unless absolutely necessary (FFI, performance-critical primitives)
- Document all safety invariants with `// SAFETY:` comments
- Encapsulate in safe public APIs

## Testing

- Unit tests: `#[cfg(test)] mod tests` in same file
- Integration tests: `tests/` directory (separate compilation)
- Property-based testing with `proptest`
- Coverage: `cargo llvm-cov` or `cargo tarpaulin`
- Target 80%+ coverage
