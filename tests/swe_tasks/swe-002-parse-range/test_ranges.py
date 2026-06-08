from ranges import parse_range


def test_single_range():
    assert parse_range("1-3") == [1, 2, 3]


def test_mixed():
    assert parse_range("1-3,5") == [1, 2, 3, 5]


def test_multiple_ranges():
    assert parse_range("1-2,7-8") == [1, 2, 7, 8]


def test_singletons():
    assert parse_range("4") == [4]
