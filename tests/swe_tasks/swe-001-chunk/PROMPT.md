`chunk(items, size)` drops elements. Splitting a 5-element list into chunks
of 2 returns `[[1,2],[3,4]]` — the trailing `[5]` is missing. Lists whose
length isn't a multiple of `size` lose their final chunk.
