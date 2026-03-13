Modeling Internal Overview
==========================

Core Concepts
-------------

The modelling API has three main layers:

1. **Description objects** (immutable by operator)

   * :class:`hermax.model.Literal`
   * :class:`hermax.model.Clause`
   * :class:`hermax.model.ClauseGroup`
   * :class:`hermax.model.Term`
   * :class:`hermax.model.PBExpr`
   * :class:`hermax.model.PBConstraint`

2. **Typed variables / containers**

   * Booleans, enums, bounded integers
   * Vectors, matrices, keyed dictionaries

3. **Model accumulation and solving**

   * ``model &= ...`` for hard constraints
   * ``model.obj[w] += ...`` for weighted soft constraints
   * ``model.tier_obj[...] += ...`` for lexicographic (tiered) objectives
   * ``model.to_cnf()``, ``model.to_wcnf()``, ``model.solve()``

Eager vs. lazy evaluation
-----------------------------------------

The API is immediate, but not everything is compiled at the same time:

* Boolean operators produce clauses/groups immediately.
* PB comparisons produce a **lazy** :class:`hermax.model.PBConstraint` which is compiled when it must be
  materialized, for example during export/solve.

This keeps the design expressive while preserving enough PB metadata for safe
operations like ``PB.implies(literal)``.

Mutability contract
-------------------

Operator syntax is **immutable by contract** for modelling objects:

* ``ClauseGroup &= ...`` returns a new ``ClauseGroup`` (it does not mutate).
* ``PBExpr += ...`` returns a new ``PBExpr`` (it does not mutate).

The only intended mutable sinks are:

* ``model &= constraint``
* ``model.obj[w] += constraint``

Inplace Mutation APIs
----------------------

For performance oriented or builder code, the model exposes explicit
mutators with a mandatory keyword guard:

* ``clause.append(lit, inplace=True)``
* ``group.extend(x, inplace=True)``
* ``expr.add(x, inplace=True)``
* ``expr.sub(x, inplace=True)``
