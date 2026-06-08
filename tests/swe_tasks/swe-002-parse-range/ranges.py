def parse_range(spec):
    """Parse a range spec like "1-3,5,7-8" into a sorted list of ints.

    Ranges are inclusive of both ends. e.g. "1-3,5" -> [1, 2, 3, 5]
    """
    out = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b)))
        else:
            out.append(int(part))
    return out
