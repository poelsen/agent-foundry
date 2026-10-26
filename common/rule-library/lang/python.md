# Language: Python

## Tooling

- **Package manager**: `uv` | **Config**: `pyproject.toml` | **Build**: `hatchling`
- **Virtual env**: `.venv/` | **Lock**: `uv.lock` (commit it)

```bash
uv sync --extra dev                   # Setup (uses uv.lock)
uv run pytest                         # Test
uv run ruff check src tests           # Lint
uv run ruff format src tests          # Format
```
## Style

PEP 8, type hints on functions, docstrings for public APIs, f-strings.

## Code Quality

- [ ] Specific exceptions (no bare `except:`)
- [ ] Context managers for resources
- [ ] `pathlib` over `os.path`
- [ ] No mutable default arguments
- [ ] Don't mutate caller's data — return new objects

## Error Handling

```python
except SpecificError as e:
    logger.error(f"Operation failed: {e}")
    raise UserFacingError("message") from e
```

## Testing

pytest + fixtures + `parametrize`.
