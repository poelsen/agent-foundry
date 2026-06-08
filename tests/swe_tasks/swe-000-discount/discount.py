def apply_discount(price, pct):
    """Return the price after applying a pct% discount.

    e.g. apply_discount(100, 10) -> 90.0
    """
    return price * pct / 100
