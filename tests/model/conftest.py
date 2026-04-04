from __future__ import annotations

import pytest

from hermax.model import Model


@pytest.fixture(autouse=True)
def _disable_merge_pb_optimization_for_model_tests(monkeypatch):
    original_init = Model.__init__

    def wrapped_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.set_merge_pb_optimization(False)

    monkeypatch.setattr(Model, "__init__", wrapped_init)
