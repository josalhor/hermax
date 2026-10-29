from hermax.model import Model


def test_fully_posted_definitions_are_not_looked_up_again(monkeypatch):
    m = Model()
    x = m.int("x", 0, 3)
    _ = x == 1
    assert m.solve(backend="sat").ok

    def unexpected_lookup(*args):
        raise AssertionError("Already posted definitions must not be looked up again")

    monkeypatch.setattr(Model, "_find_literal_by_id", unexpected_lookup)
    assert m.solve(backend="sat").ok


def test_fully_posted_definitions_do_not_require_scanning_a_group():
    class NoIteration:
        def __iter__(self):
            raise AssertionError("Already posted definitions must not scan clause groups")

    m = Model()
    x = m.int("x", 0, 3)
    _ = x == 1
    assert m.solve().ok
    m._ensure_deferred_defs_in_group(NoIteration())


def test_new_definitions_are_posted_after_earlier_definitions_were_completed():
    m = Model()
    x = m.int("x", 0, 4)
    m &= x == 1
    assert m.solve(backend="sat").ok
    m &= x == 2
    assert not m.solve(backend="sat").ok
