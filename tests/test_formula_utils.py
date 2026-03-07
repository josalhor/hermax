from pathlib import Path

import pytest
from pysat.formula import WCNF

from hermax.core.utils import normalize_wcnf_formula


def test_normalize_wcnf_formula_passthrough_pysat() -> None:
    f = WCNF()
    f.append([1, -2])
    out = normalize_wcnf_formula(f)
    assert out is f


def test_normalize_wcnf_formula_none() -> None:
    assert normalize_wcnf_formula(None) is None


def test_normalize_wcnf_formula_optilog_like_conversion() -> None:
    OptiLikeWCNF = type("WCNF", (), {"__module__": "optilog.formulas"})

    obj = OptiLikeWCNF()
    obj.hard_clauses = [[1, 2], [-2, 3]]
    obj.soft_clauses = [(4, [-1]), (2, [-3, 2])]
    obj.max_var = lambda: 3

    out = normalize_wcnf_formula(obj)
    assert isinstance(out, WCNF)
    assert out.hard == [[1, 2], [-2, 3]]
    assert out.soft == [[-1], [-3, 2]]
    assert out.wght == [4, 2]
    assert out.nv >= 3


DATA_DIR = Path(__file__).resolve().parent / "data"
WCNF_FILES = sorted(DATA_DIR.glob("*.wcnf"))


@pytest.mark.parametrize("wcnf_path", WCNF_FILES, ids=lambda p: p.name)
def test_normalize_wcnf_formula_pysat_file_passthrough(wcnf_path: Path) -> None:
    f = WCNF(from_file=str(wcnf_path))
    out = normalize_wcnf_formula(f)
    assert out is f
    assert len(out.hard) >= 0
    assert len(out.soft) == len(out.wght)


@pytest.mark.parametrize("wcnf_path", WCNF_FILES, ids=lambda p: p.name)
def test_normalize_wcnf_formula_optilog_matches_pysat_on_data(wcnf_path: Path) -> None:
    optilog_loaders = pytest.importorskip("optilog.formulas.loaders")
    load_wcnf = getattr(optilog_loaders, "load_wcnf")

    pysat_f = WCNF(from_file=str(wcnf_path))
    optilog_f = load_wcnf(str(wcnf_path))
    out = normalize_wcnf_formula(optilog_f)

    assert isinstance(out, WCNF)
    assert out.hard == pysat_f.hard
    assert out.soft == pysat_f.soft
    assert out.wght == pysat_f.wght
    assert out.nv >= pysat_f.nv
