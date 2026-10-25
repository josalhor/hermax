"""Model-local memoization for reusable construction operations."""

from functools import wraps
from inspect import Parameter, signature
from typing import Callable, Mapping


_MISSING = object()


class _Identity:
    __slots__ = ("value",)

    def __init__(self, value):
        self.value = value

    def __hash__(self):
        return id(self.value)

    def __eq__(self, other):
        return isinstance(other, _Identity) and self.value is other.value


def _key(value):
    if value is None or type(value) in (bool, int, float, str, bytes):
        return type(value), value
    if isinstance(value, (tuple, list)):
        return type(value), tuple(_key(item) for item in value)
    if isinstance(value, dict):
        return dict, frozenset((_key(k), _key(v)) for k, v in value.items())
    return _Identity(value)


def _unordered_key(values):
    counts = {}
    for value in values:
        key = _key(value)
        counts[key] = counts.get(key, 0) + 1
    return frozenset(counts.items())


class OperationCache:
    __slots__ = ("_results",)

    def __init__(self):
        self._results = {}

    def get_or_create(self, key, factory: Callable):
        result = self._results.get(key, _MISSING)
        if result is _MISSING:
            result = factory()
            self._results[key] = result
        return result


def cached_operation(
    *,
    normalize: Mapping[str, Callable] | None = None,
    unordered: tuple[str, ...] = (),
    fresh_if: str | None = "name",
):
    """Cache successful constructions; named calls bypass sharing.

    Normalizers run before lookup and supply the builder's arguments. Keys use
    typed scalar values and object identity, retaining objects for the cache's
    lifetime. Only mark functions whose results can safely be shared.
    """

    def decorate(function):
        sig = signature(function)
        parameters = tuple(sig.parameters.values())[1:]
        if any(
            p.kind in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD)
            for p in parameters
        ):
            raise TypeError("cached operations require explicit parameters")
        names = tuple(p.name for p in parameters)
        indices = {name: i for i, name in enumerate(names)}
        defaults = tuple(p.default for p in parameters)
        positional_count = sum(p.kind != Parameter.KEYWORD_ONLY for p in parameters)
        positional_only = {
            p.name for p in parameters if p.kind == Parameter.POSITIONAL_ONLY
        }
        normalizers = tuple(
            (indices[name], transform) for name, transform in (normalize or {}).items()
        )
        unordered_indices = frozenset(indices[name] for name in unordered)
        fresh_index = indices.get(fresh_if)

        @wraps(function)
        def wrapped(owner, *args, **kwargs):
            values = list(defaults)
            if len(args) > positional_count:
                return function(owner, *args, **kwargs)
            values[: len(args)] = args
            for name, value in kwargs.items():
                index = indices.get(name)
                if index is None or index < len(args) or name in positional_only:
                    sig.bind(owner, *args, **kwargs)  # Raise the normal call error.
                values[index] = value
            if any(value is Parameter.empty for value in values):
                sig.bind(owner, *args, **kwargs)
            if fresh_index is not None and values[fresh_index] is not None:
                return function(owner, *args, **kwargs)
            for index, transform in normalizers:
                values[index] = transform(values[index])
            key = (
                function,
                _Identity(owner),
                tuple(
                    _unordered_key(value) if i in unordered_indices else _key(value)
                    for i, value in enumerate(values)
                ),
            )
            model = getattr(owner, "_model", owner)
            cache = model._operation_cache
            result = cache._results.get(key, _MISSING)
            if result is _MISSING:
                result = function(
                    owner,
                    *values[:positional_count],
                    **dict(zip(names[positional_count:], values[positional_count:])),
                )
                cache._results[key] = result
            return result

        return wrapped

    return decorate
