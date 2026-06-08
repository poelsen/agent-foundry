from discount import apply_discount


def test_basic():
    assert apply_discount(100, 10) == 90


def test_zero_discount():
    assert apply_discount(50, 0) == 50


def test_full_discount():
    assert apply_discount(100, 100) == 0
