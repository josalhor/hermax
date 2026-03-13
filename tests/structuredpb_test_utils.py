from __future__ import annotations

import importlib
import importlib.util
import random
import subprocess
import sys
import sysconfig
from pathlib import Path

import pytest
from pysat.solvers import Solver


ROOT = Path(__file__).resolve().parents[1]


def _pick_solver_name() -> str:
    for name in ("cadical153", "cadical195", "g4", "g3", "m22", "mgh"):
        try:
            solver = Solver(name=name)
            solver.delete()
            return name
        except Exception:
            continue
    pytest.skip("No usable PySAT backend solver is available in this environment.")


def _build_structuredpb() -> None:
    try:
        from hermax.internal import _structuredpb  # type: ignore

        return
    except Exception:
        pass

    sources = [
        ROOT / "structuredpb" / "src" / "structuredpb_capi.cpp",
        ROOT / "structuredpb" / "src" / "mdd.cpp",
        ROOT / "structuredpb" / "src" / "gswc.cpp",
        ROOT / "structuredpb" / "src" / "ggpw.cpp",
        ROOT / "structuredpb" / "src" / "gmto.cpp",
        ROOT / "structuredpb" / "src" / "rggt.cpp",
        ROOT / "structuredpb" / "src" / "registry.cpp",
    ]
    ext_suffix = sysconfig.get_config_var("EXT_SUFFIX")
    if not ext_suffix:
        pytest.skip("Python EXT_SUFFIX is unavailable for building _structuredpb.")
    output = ROOT / "hermax" / "internal" / f"_structuredpb{ext_suffix}"
    include_dir = ROOT / "structuredpb" / "include"
    py_paths = sysconfig.get_paths()
    include_flags = []
    for inc in [str(include_dir), py_paths.get("include"), py_paths.get("platinclude")]:
        if inc:
            include_flags.extend(["-I", str(inc)])
    cmd = [
        "g++",
        "-shared",
        "-fPIC",
        "-O3",
        "-Wall",
        "-std=c++17",
        "-DNDEBUG",
        *include_flags,
        *map(str, sources),
        "-o",
        str(output),
    ]
    subprocess.run(cmd, cwd=ROOT, check=True)


def _load_native_pblib():
    try:
        from hermax.internal import _pblib  # type: ignore

        return _pblib
    except Exception:
        pass

    candidates = sorted((ROOT / "venv").rglob("_pblib*.so"))
    if not candidates:
        pytest.skip("No built native hermax.internal._pblib extension was found.")
    spec = importlib.util.spec_from_file_location("hermax.internal._pblib", candidates[0])
    if spec is None or spec.loader is None:
        pytest.skip(f"Could not import native pblib extension from {candidates[0]}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["hermax.internal._pblib"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def structuredpb_module():
    _build_structuredpb()
    importlib.invalidate_caches()
    sys.modules.pop("hermax.internal.structuredpb", None)
    sys.modules.pop("hermax.internal._structuredpb", None)
    return importlib.import_module("hermax.internal.structuredpb")


@pytest.fixture(scope="session")
def pb_baseline():
    _load_native_pblib()
    from hermax.internal.pb import EncType as PBEncType
    from hermax.internal.pb import PBEnc

    return PBEnc, PBEncType


@pytest.fixture(scope="session")
def card_baseline():
    try:
        from hermax.internal.card import CardEnc
        from hermax.internal.card import EncType as CardEncType
    except Exception as exc:
        pytest.skip(f"Card baseline is unavailable: {exc}")

    return CardEnc, CardEncType


@pytest.fixture(scope="session")
def sat_solver_name() -> str:
    return _pick_solver_name()


def assignment_units(lits: list[int], mask: int) -> list[int]:
    return [lit if (mask >> i) & 1 else -lit for i, lit in enumerate(lits)]


def expected_grouped_pb(weights: list[int], groups: list[list[int]], mask: int, bound: int) -> bool:
    total = 0
    true_lits = set()
    for i, weight in enumerate(weights):
        if (mask >> i) & 1:
            total += weight
            true_lits.add(i + 1)
    if total > bound:
        return False
    for group in groups:
        count = 0
        for lit in group:
            if lit in true_lits:
                count += 1
                if count > 1:
                    return False
    return True


def sat_under_assignment(clauses: list[list[int]], assumptions: list[int], solver_name: str) -> bool:
    with Solver(name=solver_name, bootstrap_with=clauses) as solver:
        return bool(solver.solve(assumptions=assumptions))


def partition_lits(rng: random.Random, lits: list[int]) -> list[list[int]]:
    shuffled = list(lits)
    rng.shuffle(shuffled)
    groups: list[list[int]] = []
    idx = 0
    while idx < len(shuffled):
        remaining = len(shuffled) - idx
        size = rng.randint(1, min(3, remaining))
        groups.append(sorted(shuffled[idx : idx + size]))
        idx += size
    return groups


def baseline_grouped_cnf(pb_baseline, card_baseline, lits: list[int], weights: list[int], groups: list[list[int]], bound: int):
    PBEnc, PBEncType = pb_baseline
    CardEnc, CardEncType = card_baseline
    cnf = PBEnc.leq(lits=lits, weights=weights, bound=bound, top_id=max(lits, default=0), encoding=PBEncType.bdd)
    for group in groups:
        if len(group) > 1:
            amo = CardEnc.atmost(lits=group, bound=1, encoding=CardEncType.pairwise)
            cnf.clauses.extend(amo.clauses)
            cnf.nv = max(cnf.nv, amo.nv)
    return cnf


def assert_encoding_matches_oracle_and_baseline(
    *,
    structuredpb_module,
    pb_baseline,
    card_baseline,
    sat_solver_name: str,
    encoding_name: str,
    lits: list[int],
    weights: list[int],
    groups: list[list[int]],
    bound: int,
    top_id: int | None = None,
) -> None:
    enc_type = getattr(structuredpb_module.EncType, encoding_name)
    cnf = structuredpb_module.StructuredPBEnc.leq(
        lits=lits,
        weights=weights,
        groups=groups,
        bound=bound,
        top_id=top_id,
        encoding=enc_type,
        emit_amo=True,
    )
    baseline = baseline_grouped_cnf(pb_baseline, card_baseline, lits, weights, groups, bound)

    for mask in range(1 << len(lits)):
        assumptions = assignment_units(lits, mask)
        expected = expected_grouped_pb(weights, groups, mask, bound)
        got_structured = sat_under_assignment(cnf.clauses, assumptions, sat_solver_name)
        got_baseline = sat_under_assignment(baseline.clauses, assumptions, sat_solver_name)
        assert got_structured == expected, (encoding_name, lits, weights, groups, bound, mask)
        assert got_baseline == expected, (encoding_name, lits, weights, groups, bound, mask)
        assert got_structured == got_baseline, (encoding_name, lits, weights, groups, bound, mask)


def case_id(case: dict[str, object]) -> str:
    return str(case["name"])
