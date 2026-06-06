# Template: Embedded DSP & Audio

Embedded DSP/audio systems development in C (with C++ for testing). Covers language rules, safety constraints, real-time audio processing, numerical stability, and hardware interaction.

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
- Avoid `gets`, `sprintf`, `strcpy` — use bounded variants
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
- [ ] Buffer sizes explicitly defined and checked

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

## Real-Time Audio Constraints

- [ ] Audio callback must complete within buffer period
- [ ] No memory allocation in audio thread
- [ ] No blocking calls in audio path
- [ ] No logging/printf in real-time code
- [ ] Lock-free data structures for audio thread communication

## Numerical Stability

- [ ] Fixed-point vs floating-point choice documented
- [ ] Overflow/underflow handling defined
- [ ] Saturation arithmetic where appropriate
- [ ] Filter stability verified (pole locations)
- [ ] Denormal handling (flush to zero)

## Audio Quality

- [ ] Sample rate conversions use proper interpolation
- [ ] Anti-aliasing filters where needed
- [ ] Latency budget documented
- [ ] Click/pop prevention on parameter changes (smoothing)
- [ ] Proper gain staging (headroom management)

## DSP Patterns

- [ ] Circular buffers for delay lines
- [ ] SIMD optimization where applicable
- [ ] Lookup tables for expensive functions (sin, log)
- [ ] Double-buffering for DMA transfers

## C++ for Testing

When using C++ (e.g., Google Test, Unity, CMocka) for unit tests:

- CMake preferred for test build system
- RAII for test resource management
- Smart pointers over raw pointers (`unique_ptr`, `shared_ptr`)
- Address/Thread sanitizers in CI (`-fsanitize=address`)
- Run under Valgrind for memory checks

## DSP Testing

- [ ] Unit tests with known input/output pairs
- [ ] Impulse response verification
- [ ] THD+N measurements for audio quality
- [ ] CPU load profiling under worst-case conditions
- [ ] Test edge cases: NULL inputs, zero sizes, max values

## Build

- Warnings as errors (`-Wall -Wextra -Wpedantic` minimum)
- Static analysis clean (no warnings)
- Link-time optimization for size
- Debug vs Release configs properly separated
- Assertions enabled in debug, compiled out in release

## Checklist

- [ ] Warnings clean (`-Wall -Wextra -Werror`)
- [ ] No dynamic allocation in audio processing path
- [ ] No recursion (or bounded with proof)
- [ ] Audio callback within buffer period
- [ ] Fixed-point Q-formats documented
- [ ] Saturation arithmetic for overflow protection
- [ ] SIMD optimization where applicable
- [ ] Latency budget documented
- [ ] Unit tests with known I/O pairs
- [ ] Static analysis passing
