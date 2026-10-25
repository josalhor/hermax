import gc
import weakref

import pytest

from hermax.internal.operation_cache import OperationCache, cached_operation


class Owner:
    def __init__(self):
        self._operation_cache = OperationCache()
        self.calls = 0

    @cached_operation()
    def construct(self, value, factor=2, name=None):
        self.calls += 1
        return object()

    @cached_operation(normalize={"items": tuple}, unordered=("items",))
    def aggregate(self, items, *, name=None):
        self.calls += 1
        return object()

    @cached_operation(fresh_if=None)
    def fail_once(self, value):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("construction failed")
        return None


class HostileEquality:
    def __eq__(self, other):
        raise AssertionError("object equality must not run")


def test_keywords_defaults_types_and_names():
    owner = Owner()
    first = owner.construct(3)
    assert owner.construct(value=3, factor=2, name=None) is first
    assert owner.construct(3, 2) is first
    assert owner.construct(True) is not owner.construct(1)
    assert owner.construct(3.0) is not first
    assert owner.construct(3, name="a") is not owner.construct(3, name="a")
    for call in (
        lambda: owner.construct(),
        lambda: owner.construct(3, value=3),
        lambda: owner.construct(3, unknown=2),
        lambda: owner.construct(3, 2, None, 4),
    ):
        with pytest.raises(TypeError):
            call()


def test_identity_keys_retain_objects_without_overloaded_equality():
    owner = Owner()
    a, b = HostileEquality(), HostileEquality()
    ref = weakref.ref(a)
    first = owner.construct(a)
    assert owner.construct(a) is first
    assert owner.construct(b) is not first
    del a
    gc.collect()
    assert ref() is not None
    del owner
    gc.collect()
    assert ref() is None


def test_sequences_are_snapshotted_and_multiplicity_preserved():
    owner = Owner()
    a, b = object(), object()
    inputs = [a, b, a]
    first = owner.aggregate(inputs)
    assert owner.aggregate(iter([a, a, b])) is first
    inputs[0] = b
    assert owner.aggregate(inputs) is not first
    assert owner.aggregate([a, a, b]) is first


def test_failures_are_not_cached_and_none_is_cached():
    owner = Owner()
    with pytest.raises(RuntimeError):
        owner.fail_once(1)
    assert owner.fail_once(1) is None
    assert owner.fail_once(1) is None
    assert owner.calls == 2


def test_cache_is_local_and_reusable_without_decorator():
    a, b = Owner(), Owner()
    assert a.construct(1) is not b.construct(1)
    value = object()
    assert a._operation_cache.get_or_create("key", lambda: value) is value

    def fail():
        raise AssertionError("cache miss")

    assert a._operation_cache.get_or_create("key", fail) is value


def test_model_owned_receiver_is_part_of_key():
    class Child:
        def __init__(self, model):
            self._model = model

        @cached_operation(fresh_if=None)
        def construct(self, value):
            return object()

    owner = Owner()
    a, b = Child(owner), Child(owner)
    assert a.construct(1) is a.construct(1)
    assert a.construct(1) is not b.construct(1)
