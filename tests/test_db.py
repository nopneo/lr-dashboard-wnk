import db


def test_num_string():
    assert db.num("3") == 3


def test_num_none_and_empty():
    assert db.num(None) == 0
    assert db.num("") == 0


def test_num_float_kept():
    assert db.num("2.5") == 2.5


def test_bind_tuple_param():
    assert db._bind("a in %(x)s", {"x": ("a", "b")}) == "a in ('a','b')"
