from chunk import chunk


def test_even_split():
    assert chunk([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]


def test_partial_last_chunk():
    assert chunk([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]


def test_size_larger_than_list():
    assert chunk([1], 3) == [[1]]


def test_empty():
    assert chunk([], 2) == []
