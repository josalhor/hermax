"""
HERMAX TDD TEST SUITE
The Executable Specification for the Boolean & PB Space, Int/Enum Types, and Containers.
"""

import pytest

# Note: These imports reflect the intended Stage 1/Stage 2 public types.
# PBExpr comparators finalize to a lazy PBConstraint descriptor, compilable to ClauseGroup.
from hermax.model import Model, Literal, Clause, Term, PBExpr, ClauseGroup, PBConstraint

# =====================================================================
# SECTION I: THE MODEL REGISTRY & CROSS-MODEL SAFETY
# =====================================================================

def test_variable_creation_and_registry():
    model = Model()
    a = model.bool("a")
    
    assert isinstance(a, Literal)
    assert a.name == "a"
    
    # Strict Registry Rule: No silent overwriting
    with pytest.raises(ValueError, match="already registered"):
        model.bool("a")

def test_anonymous_variables():
    model = Model()
    a = model.bool()
    b = model.bool()
    
    assert a.name is not None
    assert a.name != b.name
    assert a.id != b.id

def test_cross_model_pollution_banned():
    model_A = Model()
    model_B = Model()
    
    a = model_A.bool("a")
    b = model_B.bool("b")
    
    with pytest.raises(ValueError, match="different models"):
        _ = a | b

# =====================================================================
# SECTION II: BOOLEAN PRIMITIVES & STRICT CNF
# =====================================================================

def test_literal_negation_o1():
    model = Model()
    a = model.bool("a")
    not_a = ~a
    
    assert isinstance(not_a, Literal)
    assert not_a.polarity is not a.polarity
    assert ~~a is a  # Identity perfectly preserved

def test_disjunction_and_clause_promotion():
    model = Model()
    a, b, c = model.bool("a"), model.bool("b"), model.bool("c")
    
    clause_ab = a | b
    assert isinstance(clause_ab, Clause)
    assert len(clause_ab.literals) == 2
    
    clause_abc = clause_ab | c
    assert len(clause_abc.literals) == 3
    assert len(clause_ab.literals) == 2  # Immutability check

def test_clause_inplace_or():
    model = Model()
    a, b, c = model.bool("a"), model.bool("b"), model.bool("c")
    
    c1 = a | b
    original_id = id(c1)
    c2 = c1
    c2 |= c
    
    assert len(c1.literals) == 2
    assert id(c1) == original_id
    assert len(c2.literals) == 3
    assert id(c2) != original_id  # Immutable-by-operator rebinding semantics

def test_guardrails_no_detection_no_dnf():
    model = Model()
    a, b = model.bool("a"), model.bool("b")
    
    # Literal conjunction builds an explicit ClauseGroup of unit clauses.
    g = a & b
    assert isinstance(g, ClauseGroup)
    assert len(g.clauses) == 2
        
    with pytest.raises(TypeError, match="Cannot directly negate a Clause"):
        _ = ~(a | b)

# =====================================================================
# SECTION III: PSEUDO-BOOLEAN (PB) BOOTSTRAPPING & ARITHMETIC
# =====================================================================

def test_term_creation_dunders():
    model = Model()
    a = model.bool("a")
    
    t1 = 3 * a
    t2 = a * 5
    
    assert isinstance(t1, Term)
    assert t1.coefficient == 3
    assert t2.coefficient == 5
    
    with pytest.raises(TypeError):
        _ = t1 * t2  # Non-linear math banned

def test_literal_plus_literal_bootstrapping():
    model = Model()
    a, b = model.bool("a"), model.bool("b")
    
    # The crucial fix: Lit + Lit -> PBExpr
    expr = a + b
    assert isinstance(expr, PBExpr)
    assert len(expr.terms) == 2
    assert expr.terms[0].coefficient == 1

def test_pbexpr_arithmetic_and_promotion():
    model = Model()
    a, b, c = model.bool("a"), model.bool("b"), model.bool("c")
    
    expr = (2 * a) + b - c
    assert isinstance(expr, PBExpr)
    assert len(expr.terms) == 3
    # Checking negative auto-normalization logic conceptually
    # '-c' should be handled within PBExpr constraints without crashing

def test_pb_comparison_creation_and_rhs_shifting():
    model = Model()
    a, b, c, d = model.bool("a"), model.bool("b"), model.bool("c"), model.bool("d")
    
    expr1 = a + b
    expr2 = c + d
    
    # PBExpr <= int finalizes lazily (descriptor + on-demand clause compilation)
    constr1 = expr1 <= 2
    assert isinstance(constr1, PBConstraint)
    assert isinstance(constr1.clauses(), ClauseGroup)
    
    # PBExpr <= PBExpr (RHS shifting is internal implementation detail)
    constr2 = expr1 <= expr2
    assert isinstance(constr2, PBConstraint)
    assert isinstance(constr2.clauses(), ClauseGroup)

# =====================================================================
# SECTION IV: EXPLICIT STRUCTURES & MODIFIERS (THE GOLDEN RULE)
# =====================================================================

def test_only_if_reverse_thinking():
    model = Model()
    a, b, cond = model.bool("a"), model.bool("b"), model.bool("cond")
    
    # Clause enforced by Lit
    c1 = (a | b).only_if(cond)
    assert isinstance(c1, Clause)
    
    # PB comparison finalizes to PBConstraint, which can be gated by a Literal
    pb1 = (a + b <= 1).only_if(cond)
    assert isinstance(pb1, PBConstraint)
    assert isinstance(pb1.clauses(), ClauseGroup)
    
    # DETECTION BANNED
    with pytest.raises(TypeError, match="must be a Literal"):
        _ = (a | b).only_if(a + b <= 1)

def test_implies_forward_thinking():
    model = Model()
    a, b, c = model.bool("a"), model.bool("b"), model.bool("c")
    
    # Lit enforces Lit -> Clause
    c1 = a.implies(b)
    assert isinstance(c1, Clause)
    
    # Lit enforces a PB comparison result (lazy PBConstraint)
    pb1 = a.implies(b + c <= 1)
    assert isinstance(pb1, PBConstraint)
    assert isinstance(pb1.clauses(), ClauseGroup)
    
    # Clause enforces Target -> ClauseGroup
    cg = (a | b).implies(c)
    assert isinstance(cg, ClauseGroup)
    
    # PB antecedent implying a literal is supported via contrapositive rewrite.
    pb2 = (a + b <= 1).implies(c)
    assert isinstance(pb2, (PBConstraint, ClauseGroup))

# =====================================================================
# SECTION V: OBJECTIVES AND HARD CLAUSE COMPILATION
# =====================================================================

def test_hard_vs_soft_assignment_syntax():
    model = Model()
    a, b = model.bool("a"), model.bool("b")
    
    # Stage 2 compilation trigger tests (Mocked internally by the API)
    model &= (a | b)
    model &= (a + b <= 1)
    
    # Soft constraint bucket check
    model.obj[100] += (a + b <= 1)
    # The architecture should seamlessly spin up the relaxation variable `r`
    # and assign the penalty to `~r` internally.

# =====================================================================
# SECTION VI: INT AND ENUM TYPES
# =====================================================================

def test_enum_declarations_and_equality():
    model = Model()
    color1 = model.enum("color1", choices=["red", "green", "blue"], nullable=True)
    color2 = model.enum("color2", choices=["red", "green", "blue"])
    
    # Literal mapping O(1)
    assert isinstance(color1 == "red", Literal)
    
    # Equality between Enums (Pairwise Strict CNF)
    eq_constr = (color1 == color2)
    assert isinstance(eq_constr, ClauseGroup)

def test_int_declarations_and_fast_inequalities():
    model = Model()
    speed = model.int("speed", lb=0, ub=10)
    
    # Discrete inclusive lookup O(1)
    assert isinstance(speed <= 5, Literal)
    assert isinstance(speed >= 3, Literal)
    
    # Strict inequalities shift to inclusive equivalents
    lt_lit = (speed < 5)
    assert isinstance(lt_lit, Literal) # Maps internally to speed <= 4
    
    gt_lit = (speed > 5)
    assert isinstance(gt_lit, Literal) # Maps internally to ~speed <= 5

def test_int_unary_summation_promotion():
    model = Model()
    a = model.bool("a")
    speed = model.int("speed", lb=0, ub=4)
    
    # Int + Bool unrolls the ladder
    expr = a + speed
    assert isinstance(expr, PBExpr)
    # 4 ladder bits + 1 bool = 5 terms
    assert len(expr.terms) == 5 
    
    # Int * int distributes scalar across ladder
    scaled = 3 * speed
    assert isinstance(scaled, PBExpr)
    assert len(scaled.terms) == 4
    assert scaled.terms[0].coefficient == 3

# =====================================================================
# SECTION VII: HIGH-ORDER CONTAINERS (VECTORS & MATRICES)
# =====================================================================

def test_container_creation_and_registry():
    model = Model()
    
    v_bool = model.bool_vector("v_bool", length=5)
    v_int = model.int_vector("v_int", length=5, lb=0, ub=10)
    v_enum = model.enum_vector("v_enum", length=5, choices=["A", "B"])
    
    # Name collision rule strictly applies to containers too
    with pytest.raises(ValueError):
        model.bool_vector("v_int", length=5)

def test_matrix_slicing():
    model = Model()
    grid = model.int_matrix("grid", rows=9, cols=9, lb=1, ub=9)
    
    row0 = grid.row(0)
    col0 = grid.col(0)
    
    # Should return typed Vector views
    assert len(row0) == 9
    assert len(col0) == 9

def test_vector_global_constraints():
    model = Model()
    v_int = model.int_vector("v", length=5, lb=0, ub=10)
    
    assert isinstance(v_int.all_different(), ClauseGroup) # Or an internal global constraint object
    assert isinstance(v_int.increasing(), ClauseGroup)
    
    v2 = model.int_vector("v2", length=5, lb=0, ub=10)
    
    # Explicit lexicographic
    lex = v_int.lexicographic_less_than(v2)
    assert isinstance(lex, ClauseGroup)

def test_vector_operator_overloads():
    model = Model()
    v1 = model.int_vector("v1", length=5, lb=0, ub=10)
    v2 = model.int_vector("v2", length=5, lb=0, ub=10)
    
    # Vector Equality Banned (As requested)
    with pytest.raises(TypeError):
        _ = (v1 == v2)
        
    # Vector Inequality Banned (Element-wise/Lexicographic ambiguity)
    with pytest.raises(TypeError, match="lexicographic_less_than"):
        _ = (v1 <= v2)
        
    # Vector != returns a single flat disjunction of differences
    diff_clause = (v1 != v2)
    assert isinstance(diff_clause, Clause)
