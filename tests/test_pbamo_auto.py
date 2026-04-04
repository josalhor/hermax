from __future__ import annotations

from pysat.solvers import Solver

from tests.pbamo_test_utils import assignment_units


def _baseline_overlap_cnf(pb_baseline, *, lits, weights, bound, amo_groups, eo_groups):
    PBEnc, PBEncType = pb_baseline
    cnf = PBEnc.leq(lits=lits, weights=weights, bound=bound, top_id=max(lits, default=0), encoding=PBEncType.bdd)
    for group in amo_groups:
        uniq = sorted({int(lit) for lit in group})
        for i in range(len(uniq)):
            for j in range(i + 1, len(uniq)):
                cnf.clauses.append([-uniq[i], -uniq[j]])
    for group in eo_groups:
        uniq = sorted({int(lit) for lit in group})
        for i in range(len(uniq)):
            for j in range(i + 1, len(uniq)):
                cnf.clauses.append([-uniq[i], -uniq[j]])
        if uniq:
            cnf.clauses.append(list(uniq))
    return cnf


def _expected_overlap_pb(*, lits, weights, amo_groups, eo_groups, bound, mask):
    true_lits = {lit for lit, bit in zip(lits, range(len(lits))) if (mask >> bit) & 1}
    total = sum(weight for lit, weight in zip(lits, weights) if lit in true_lits)
    if total > bound:
        return False
    for group in amo_groups:
        if sum(1 for lit in group if lit in true_lits) > 1:
            return False
    for group in eo_groups:
        if sum(1 for lit in group if lit in true_lits) != 1:
            return False
    return True


def _sat_under_assignment(clauses, assumptions, solver_name):
    with Solver(name=solver_name, bootstrap_with=clauses) as solver:
        return bool(solver.solve(assumptions=assumptions))


def test_choose_portfolio_stage1_rule(pbamo_module) -> None:
    assert pbamo_module.choose_portfolio([1, 2, 3], [1, 1, 1], [[1], [2], [3]], 2) == "pblib"
    assert pbamo_module.choose_portfolio(list(range(1, 8)), [1] * 7, [[1, 2], [3], [4], [5], [6], [7]], 3) == "pblib"
    assert (
        pbamo_module.choose_portfolio(
            list(range(1, 13)),
            [2] * 12,
            [[1, 2], [3], [4], [5], [6], [7], [8], [9], [10], [11], [12]],
            8,
    )
        == "pbamo"
    )


def test_choose_cardinality_portfolio_rule(pbamo_module) -> None:
    assert (
        pbamo_module.choose_cardinality_portfolio(
            list(range(1, 13)),
            [[1, 2], [3], [4], [5], [6], [7], [8], [9], [10], [11], [12]],
            5,
        )
        == "card"
    )
    assert (
        pbamo_module.choose_cardinality_portfolio(
            list(range(1, 13)),
            [[1, 2, 3], [4, 5, 6], [7, 8, 9], [10, 11, 12]],
            3,
        )
        == "pbamo"
    )


def test_amo_upper_bound_uses_actual_literal_ids(pbamo_module) -> None:
    assert pbamo_module.amo_upper_bound([11, 7, 3], [[10, 20], [30]], lits=[30, 10, 20]) == 18


def test_overlap_partition_dynamic_future_beats_paper_baseline_on_known_case(pbamo_module) -> None:
    lits = [1, 2, 3, 4, 5, 6]
    weights = [5, 5, 5, 4, 4, 4]
    amo_groups = [[1, 2, 4], [2, 3, 5], [1, 3, 6], [4, 5], [5, 6]]

    baseline = pbamo_module.choose_overlap_partition(
        lits,
        weights,
        amo_groups=amo_groups,
        eo_groups=[],
        policy=pbamo_module.OverlapPolicy.baseline_paper,
    )
    improved = pbamo_module.choose_overlap_partition(
        lits,
        weights,
        amo_groups=amo_groups,
        eo_groups=[],
        policy=pbamo_module.OverlapPolicy.paper_best_fit_dynamic_future,
    )

    assert baseline == [[1, 2, 3], [4, 5], [6]]
    assert improved == [[1, 2, 4], [3, 5, 6]]
    assert pbamo_module.amo_upper_bound(weights, improved, lits=lits) < pbamo_module.amo_upper_bound(
        weights, baseline, lits=lits
    )


def test_auto_leq_routes_to_pblib(monkeypatch, pbamo_module) -> None:
    import hermax.internal.pb as pb_mod

    called = {"pblib": 0, "structured": 0}
    orig_pb_leq = pb_mod.PBEnc.leq
    orig_structured_leq = pbamo_module.PBAMOEnc.leq

    def wrapped_pb(*args, **kwargs):
        called["pblib"] += 1
        return orig_pb_leq(*args, **kwargs)

    def wrapped_structured(*args, **kwargs):
        called["structured"] += 1
        return orig_structured_leq(*args, **kwargs)

    monkeypatch.setattr(pb_mod.PBEnc, "leq", staticmethod(wrapped_pb))
    monkeypatch.setattr(pbamo_module.PBAMOEnc, "leq", classmethod(lambda cls, *a, **kw: wrapped_structured(*a, **kw)))

    pbamo_module.PBAMOEnc.auto_leq(
        lits=[1, 2, 3, 4],
        weights=[3, 5, 7, 9],
        bound=10,
        amo_groups=[[1, 2], [2, 3]],
    )

    assert called == {"pblib": 1, "structured": 0}


def test_auto_leq_unit_weights_routes_to_card(monkeypatch, pbamo_module) -> None:
    import hermax.internal.card as card_mod

    called = {"card": 0, "structured": 0}
    orig_card_atmost = card_mod.CardEnc.atmost
    orig_structured_leq = pbamo_module.PBAMOEnc.leq

    def wrapped_card(*args, **kwargs):
        called["card"] += 1
        return orig_card_atmost(*args, **kwargs)

    def wrapped_structured(*args, **kwargs):
        called["structured"] += 1
        return orig_structured_leq(*args, **kwargs)

    monkeypatch.setattr(card_mod.CardEnc, "atmost", staticmethod(wrapped_card))
    monkeypatch.setattr(pbamo_module.PBAMOEnc, "leq", classmethod(lambda cls, *a, **kw: wrapped_structured(*a, **kw)))

    pbamo_module.PBAMOEnc.auto_leq(
        lits=list(range(1, 13)),
        weights=[1] * 12,
        bound=5,
        groups=[[1, 2], [3], [4], [5], [6], [7], [8], [9], [10], [11], [12]],
    )

    assert called == {"card": 1, "structured": 0}


def test_auto_leq_unit_weights_routes_to_structured(monkeypatch, pbamo_module) -> None:
    import hermax.internal.card as card_mod

    called = {"card": 0, "structured": 0}
    orig_card_atmost = card_mod.CardEnc.atmost
    orig_structured_leq = pbamo_module.PBAMOEnc.leq

    def wrapped_card(*args, **kwargs):
        called["card"] += 1
        return orig_card_atmost(*args, **kwargs)

    def wrapped_structured(*args, **kwargs):
        called["structured"] += 1
        return orig_structured_leq(*args, **kwargs)

    monkeypatch.setattr(card_mod.CardEnc, "atmost", staticmethod(wrapped_card))
    monkeypatch.setattr(pbamo_module.PBAMOEnc, "leq", classmethod(lambda cls, *a, **kw: wrapped_structured(*a, **kw)))

    pbamo_module.PBAMOEnc.auto_leq(
        lits=list(range(1, 13)),
        weights=[1] * 12,
        bound=3,
        groups=[[1, 2, 3], [4, 5, 6], [7, 8, 9], [10, 11, 12]],
    )

    assert called == {"card": 0, "structured": 1}


def test_auto_leq_unit_weights_routes_through_cardinality_path(monkeypatch, pbamo_module) -> None:
    import hermax.internal.card as card_mod
    import hermax.internal.pb as pb_mod

    called = {"card": 0, "pb": 0, "structured": 0}
    orig_card_atmost = card_mod.CardEnc.atmost
    orig_pb_leq = pb_mod.PBEnc.leq
    orig_structured_leq = pbamo_module.PBAMOEnc.leq

    def wrapped_card(*args, **kwargs):
        called["card"] += 1
        return orig_card_atmost(*args, **kwargs)

    def wrapped_pb(*args, **kwargs):
        called["pb"] += 1
        return orig_pb_leq(*args, **kwargs)

    def wrapped_structured(*args, **kwargs):
        called["structured"] += 1
        return orig_structured_leq(*args, **kwargs)

    monkeypatch.setattr(card_mod.CardEnc, "atmost", staticmethod(wrapped_card))
    monkeypatch.setattr(pb_mod.PBEnc, "leq", staticmethod(wrapped_pb))
    monkeypatch.setattr(pbamo_module.PBAMOEnc, "leq", classmethod(lambda cls, *a, **kw: wrapped_structured(*a, **kw)))

    pbamo_module.PBAMOEnc.auto_leq(
        lits=list(range(1, 13)),
        weights=[1] * 12,
        bound=5,
        groups=[[1, 2], [3], [4], [5], [6], [7], [8], [9], [10], [11], [12]],
    )

    assert called == {"card": 1, "pb": 0, "structured": 0}


def test_auto_leq_routes_to_structured(monkeypatch, pbamo_module) -> None:
    import hermax.internal.pb as pb_mod

    called = {"pblib": 0, "structured": 0}
    orig_pb_leq = pb_mod.PBEnc.leq
    orig_structured_leq = pbamo_module.PBAMOEnc.leq

    def wrapped_pb(*args, **kwargs):
        called["pblib"] += 1
        return orig_pb_leq(*args, **kwargs)

    def wrapped_structured(*args, **kwargs):
        called["structured"] += 1
        return orig_structured_leq(*args, **kwargs)

    monkeypatch.setattr(pb_mod.PBEnc, "leq", staticmethod(wrapped_pb))
    monkeypatch.setattr(pbamo_module.PBAMOEnc, "leq", classmethod(lambda cls, *a, **kw: wrapped_structured(*a, **kw)))

    pbamo_module.PBAMOEnc.auto_leq(
        lits=list(range(1, 13)),
        weights=[3, 7, 4, 8, 5, 9, 6, 10, 7, 11, 8, 12],
        bound=35,
        amo_groups=[[1, 2, 3], [2, 3, 4], [5, 6], [6, 7, 8], [9, 10], [10, 11, 12]],
    )

    assert called == {"pblib": 0, "structured": 1}


def test_auto_eq_routes_to_pblib_equals(monkeypatch, pbamo_module) -> None:
    import hermax.internal.pb as pb_mod

    called = {"pblib_eq": 0, "structured_leq": 0}
    orig_pb_eq = pb_mod.PBEnc.equals
    orig_structured_leq = pbamo_module.PBAMOEnc.leq

    def wrapped_pb_eq(*args, **kwargs):
        called["pblib_eq"] += 1
        return orig_pb_eq(*args, **kwargs)

    def wrapped_structured(*args, **kwargs):
        called["structured_leq"] += 1
        return orig_structured_leq(*args, **kwargs)

    monkeypatch.setattr(pb_mod.PBEnc, "equals", staticmethod(wrapped_pb_eq))
    monkeypatch.setattr(
        pbamo_module.PBAMOEnc,
        "leq",
        classmethod(lambda cls, *a, **kw: wrapped_structured(*a, **kw)),
    )

    pbamo_module.PBAMOEnc.auto_eq(
        lits=[1, 2, 3, 4],
        weights=[3, 5, 7, 9],
        bound=10,
    )

    assert called == {"pblib_eq": 1, "structured_leq": 0}


def test_auto_eq_routes_to_structured_when_overlap_is_nontrivial(monkeypatch, pbamo_module) -> None:
    import hermax.internal.pb as pb_mod

    called = {"pblib_eq": 0, "structured_leq": 0}
    orig_pb_eq = pb_mod.PBEnc.equals
    orig_structured_leq = pbamo_module.PBAMOEnc.leq

    def wrapped_pb_eq(*args, **kwargs):
        called["pblib_eq"] += 1
        return orig_pb_eq(*args, **kwargs)

    def wrapped_structured(*args, **kwargs):
        called["structured_leq"] += 1
        return orig_structured_leq(*args, **kwargs)

    monkeypatch.setattr(pb_mod.PBEnc, "equals", staticmethod(wrapped_pb_eq))
    monkeypatch.setattr(
        pbamo_module.PBAMOEnc,
        "leq",
        classmethod(lambda cls, *a, **kw: wrapped_structured(*a, **kw)),
    )

    pbamo_module.PBAMOEnc.auto_eq(
        lits=list(range(1, 13)),
        weights=[3, 7, 4, 8, 5, 9, 6, 10, 7, 11, 8, 12],
        bound=35,
        amo_groups=[[1, 2, 3], [2, 3, 4], [5, 6], [6, 7, 8], [9, 10], [10, 11, 12]],
    )

    assert called["pblib_eq"] == 0
    assert called["structured_leq"] >= 1


def test_auto_leq_overlap_semantics_pblib_branch(pbamo_module, pb_baseline, sat_solver_name: str) -> None:
    lits = [1, 2, 3, 4, 5]
    weights = [2, 5, 7, 3, 4]
    amo_groups = [[1, 2], [2, 3], [4, 5]]
    eo_groups = [[3, 4]]
    bound = 9

    cnf = pbamo_module.PBAMOEnc.auto_leq(
        lits=lits,
        weights=weights,
        bound=bound,
        amo_groups=amo_groups,
        eo_groups=eo_groups,
    )
    baseline = _baseline_overlap_cnf(pb_baseline, lits=lits, weights=weights, bound=bound, amo_groups=amo_groups, eo_groups=eo_groups)

    for mask in range(1 << len(lits)):
        assumptions = assignment_units(lits, mask)
        expected = _expected_overlap_pb(
            lits=lits, weights=weights, amo_groups=amo_groups, eo_groups=eo_groups, bound=bound, mask=mask
        )
        assert _sat_under_assignment(cnf.clauses, assumptions, sat_solver_name) == expected
        assert _sat_under_assignment(baseline.clauses, assumptions, sat_solver_name) == expected


def test_auto_leq_overlap_semantics_structured_branch(
    pbamo_module, pb_baseline, sat_solver_name: str
) -> None:
    lits = list(range(1, 13))
    weights = [3, 7, 4, 8, 5, 9, 6, 10, 7, 11, 8, 12]
    amo_groups = [[1, 2, 3], [2, 3, 4], [5, 6], [6, 7, 8], [9, 10], [10, 11, 12]]
    eo_groups = [[1, 4], [7, 8]]
    bound = 35

    cnf = pbamo_module.PBAMOEnc.auto_leq(
        lits=lits,
        weights=weights,
        bound=bound,
        amo_groups=amo_groups,
        eo_groups=eo_groups,
    )
    baseline = _baseline_overlap_cnf(pb_baseline, lits=lits, weights=weights, bound=bound, amo_groups=amo_groups, eo_groups=eo_groups)

    for mask in range(1 << len(lits)):
        assumptions = assignment_units(lits, mask)
        expected = _expected_overlap_pb(
            lits=lits, weights=weights, amo_groups=amo_groups, eo_groups=eo_groups, bound=bound, mask=mask
        )
        assert _sat_under_assignment(cnf.clauses, assumptions, sat_solver_name) == expected
        assert _sat_under_assignment(baseline.clauses, assumptions, sat_solver_name) == expected
