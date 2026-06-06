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

## pyproject.toml Essentials

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "myproject"
version = "0.1.0"
requires-python = ">=3.11"

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-cov>=4", "ruff>=0.8"]

[tool.ruff]
target-version = "py311"
line-length = 100
select = ["E", "W", "F", "I", "B", "C4", "UP", "SIM", "PTH", "RUF"]
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

pytest + fixtures + `parametrize`. Coverage target: 80%+.
