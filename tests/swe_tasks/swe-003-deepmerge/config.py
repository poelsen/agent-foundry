def merge_config(base, override):
    """Merge `override` on top of `base` and return the result.

    - Nested dicts are merged recursively (not replaced wholesale).
    - `base` must NOT be mutated; callers reuse it.

    e.g. merge_config({"db": {"host": "x", "port": 5432}}, {"db": {"port": 6000}})
         -> {"db": {"host": "x", "port": 6000}}
    """
    result = base
    for key, value in override.items():
        result[key] = value
    return result
