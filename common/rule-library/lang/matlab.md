# Language: MATLAB

## Vectorization

- Prefer vectorized operations over loops — orders of magnitude faster
- Use element-wise operators (`.*`, `./`, `.^`) for array math
- Replace `for` loops with `arrayfun`, `cellfun`, `bsxfun` where readable
- Use logical indexing: `x(x > threshold)` instead of looping with `if`
- Preallocate arrays before loops: `result = zeros(1, n)`

## Naming Conventions

- `camelCase` for variables and functions
- `UPPER_SNAKE_CASE` for constants
- Prefix boolean variables: `isValid`, `hasData`, `canProcess`
- Descriptive names — avoid single letters except loop indices and math notation
- Function name matches filename exactly

## File Organization

```
src/           # Main source functions
+package/      # Package directories (namespacing)
tests/         # Test files
data/          # Sample/test data
docs/          # Documentation
```

- One function per file (MATLAB convention)
- Use packages (`+pkg/`) to namespace related functions
- Keep scripts separate from functions
- Use `private/` directories for internal helpers

## Toolbox Usage

- Document required toolboxes in project README
- Check toolbox availability: `license('test', 'Signal_Toolbox')`
- Prefer built-in functions over toolbox when both exist
- Wrap toolbox-specific calls for portability

## Error Handling

- Use `error()` with message IDs: `error('MyPkg:invalidInput', 'msg')`
- Validate inputs with `arguments` block (R2019b+):

```matlab
function result = process(data, options)
    arguments
        data (:,:) double
        options.Threshold (1,1) double = 0.5
        options.Method string = "default"
    end
end
```

- Use `try/catch` with `MException` for recoverable errors
- Use `validateattributes` for complex input validation

## Performance

- Profile before optimizing: `profile on`, run code, `profile viewer`
- Avoid growing arrays in loops (preallocate)
- Use `sparse()` for large matrices with few nonzero elements
- Consider `gpuArray` for parallelizable numeric operations
- Use `parfor` for embarrassingly parallel loops

## Testing

- Use MATLAB Unit Testing Framework (`matlab.unittest`)
- Test files: `tests/test_*.m` or `tests/*Test.m`
- Use parameterized tests for multiple input scenarios
- Verify numerical results with tolerance: `verifyEqual(actual, expected, 'AbsTol', 1e-10)`
