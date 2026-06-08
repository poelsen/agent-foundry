Two bugs are reported in `merge_config(base, override)`:

1. Nested dicts are clobbered instead of merged: merging `{"db": {"port": 6000}}`
   over `{"db": {"host": "x", "port": 5432}}` loses the `host` key.
2. It mutates the caller's `base` dict, corrupting config that other code reuses.

It should return a new config with nested dicts merged recursively and leave
`base` untouched.
