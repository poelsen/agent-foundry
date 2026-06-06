# Template: Embedded C/C++

Embedded systems development in C (with C++ for testing). Covers language rules, safety constraints, memory management, and hardware interaction.

## C Language

- Target C11 (or C99 where required by toolchain)
- Compile with `-Wall -Wextra -Werror -pedantic`
- Use static analysis (cppcheck, clang-tidy, PC-lint, or Coverity)

### Memory Safety

- Every `malloc` must have a corresponding `free` on all paths
- Check return value of `malloc` — never assume success
- Set pointers to `NULL` after `free`
- Use `sizeof(*ptr)` not `sizeof(type)` in allocations
- Prefer stack allocation for small, fixed-size data
- Use init/cleanup function pairs for resource management

### Defensive Coding

- Validate all function parameters (assert or early return)
- Check return values of all system/library calls
- Use `const` liberally — especially for function parameters
- Prefer `size_t` for sizes and indices
- Avoid `gets`, `sprintf`, `strcpy` — use bounded variants (`fgets`, `snprintf`, `strncpy`)
- No VLAs in production code

### File Organization

```
include/       # Public headers (.h)
src/           # Implementation (.c) + internal headers
tests/         # Test files
```

- One module = one `.c` + one `.h`
- Header guards: `#ifndef PROJECT_MODULE_H` / `#define` / `#endif`
- Forward declarations over unnecessary includes

### Naming

- `snake_case` for functions and variables
- `UPPER_SNAKE_CASE` for macros and constants
- Prefix public API with module name: `parser_init()`, `parser_free()`
- Prefix private/static functions with `_` or keep `static`

### Error Handling

- Return error codes (0 = success, negative = error)
- Use `enum` for error codes, not raw integers
- Goto-based cleanup for multi-resource functions

## Embedded Safety

- MISRA C guidelines where applicable
- No dynamic memory allocation (`malloc`/`free`) in production
- No recursion (or bounded with proof)
- All variables initialized at declaration
- Fixed-width integers (`uint8_t`, `int32_t`, etc.)
- Explicit signedness; careful with implicit promotions
- `sizeof()` for buffer sizes, not magic numbers
- Static functions for file-local scope
- Structs for related data, not parallel arrays
- Enums over `#define` for related constants

### Embedded Memory

- [ ] No buffer overflows (bounds checking on all array access)
- [ ] No unbounded loops without timeout
- [ ] Stack usage analyzed (no deep recursion)
- [ ] Heap fragmentation considered (prefer static allocation)
- [ ] Volatile for hardware registers and shared variables
- [ ] Packed structs only when necessary (with documentation)
- [ ] Alignment requirements respected

### Resource Constraints

- [ ] RAM usage tracked and budgeted
- [ ] Flash/ROM usage monitored
- [ ] CPU cycles considered for real-time requirements
- [ ] Power consumption implications noted

### Reliability

- [ ] Watchdog timer integration
- [ ] Error recovery paths defined
- [ ] Graceful degradation on resource exhaustion
- [ ] No blocking calls in ISRs
- [ ] Interrupt latency considered

### Hardware Interaction

- [ ] Volatile for hardware registers
- [ ] Memory barriers where needed
- [ ] Endianness handled explicitly
- [ ] Peripheral initialization order documented

### Defensive Programming

- [ ] Assert preconditions (compiled out in release)
- [ ] Check return values
- [ ] Default cases in switch statements
- [ ] Null pointer checks on API boundaries

## C++ for Testing

When using C++ (e.g., Google Test, Unity, CMocka) for unit tests:

- CMake preferred for test build system
- RAII for test resource management
- Smart pointers over raw pointers (`unique_ptr`, `shared_ptr`)
- `std::optional` over null/sentinel values
- Header guards or `#pragma once`
- Compiler warnings as errors (`-Werror`/`-WX`)
- Address/Thread sanitizers in CI (`-fsanitize=address`)
- Run under Valgrind for memory checks
- Test edge cases: NULL inputs, zero sizes, max values

## Build

- Warnings as errors (`-Wall -Wextra -Wpedantic` minimum)
- Static analysis clean (no warnings)
- Link-time optimization for size
- Debug vs Release configs properly separated
- Debug interfaces disabled in production builds
- Assertions enabled in debug, compiled out in release

## Checklist

- [ ] Warnings clean (`-Wall -Wextra -Werror`)
- [ ] No dynamic allocation in production code
- [ ] No recursion (or bounded with proof)
- [ ] Fixed-width integers used consistently
- [ ] Volatile for hardware registers
- [ ] Memory and stack budgets tracked
- [ ] Static analysis passing
- [ ] Unit tests passing under sanitizers
