def chunk(items, size):
    """Split `items` into consecutive lists of length `size`.

    The final chunk may be shorter if len(items) is not a multiple of size.
    e.g. chunk([1,2,3,4,5], 2) -> [[1,2],[3,4],[5]]
    """
    out = []
    for i in range(0, len(items) - size, size):
        out.append(items[i:i + size])
    return out
