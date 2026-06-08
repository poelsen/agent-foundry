from config import merge_config


def test_shallow_add():
    assert merge_config({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}


def test_override_scalar():
    assert merge_config({"a": 1}, {"a": 9}) == {"a": 9}


def test_nested_merge_keeps_siblings():
    base = {"db": {"host": "x", "port": 5432}}
    out = merge_config(base, {"db": {"port": 6000}})
    assert out == {"db": {"host": "x", "port": 6000}}


def test_base_not_mutated():
    base = {"a": 1, "nested": {"x": 1}}
    merge_config(base, {"a": 2, "nested": {"y": 2}})
    assert base == {"a": 1, "nested": {"x": 1}}
