`parse_range` is meant to expand inclusive ranges, but the upper bound is
being dropped. `parse_range("1-3")` returns `[1, 2]` instead of `[1, 2, 3]`.
Ranges should include both endpoints.
