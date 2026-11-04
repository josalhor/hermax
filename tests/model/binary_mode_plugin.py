"""Opt-in stress runner: ``pytest -p tests.model.binary_mode_plugin tests/model``.

This deliberately changes defaults for existing tests. Order-specific size,
propagation, routing, and private-storage assertions are expected to fail.
"""


def pytest_addoption(parser):
    parser.addoption("--binary-prewarm", action="store_true",
                     help="Materialize scalar predicates for small-domain external-SAT tests before export.")


def pytest_configure(config):
    from hermax.model import Model
    from hermax.model.variables import IntVar

    original_model = Model.__init__

    def initialize(self, *args, **kwargs):
        original_model(self, *args, **kwargs)
        self.set_integer_binary_threshold(4)

    Model.__init__ = initialize
    if config.getoption("--binary-prewarm"):
        original_integer = IntVar.__init__

        def initialize_integer(self, *args, **kwargs):
            original_integer(self, *args, **kwargs)
            if self.encoding == "binary" and self.ub-self.lb+1 <= 64:
                for value in range(self.lb+1,self.ub+1):
                    self._model._ensure_literal_def_realized(self >= value)
                for value in range(self.lb,self.ub+1):
                    self._model._ensure_literal_def_realized(self == value)

        IntVar.__init__ = initialize_integer
