# Codemaps

Applies only to projects with a `codemaps/` directory; don't create one unasked.

- Before changing an unfamiliar module, read `codemaps/INDEX.md`, then that module's codemap. Not all of them.
- After a structural change (new module, changed public API, new dependency), run `/update-codemaps`; it regenerates only stale maps.
