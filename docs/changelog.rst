Changelog
=========

Version 1.2.5
-------------

Highlights
~~~~~~~~~~
* Added ``time_limit`` support for incremental pySAT.
* Fixed an ``ERROR`` return from ``time_limit`` in MaxSAT.

Version 1.2.4
-------------

Highlights
~~~~~~~~~~
* Added ``time_limit`` support to model, portfolio, and subprocess solve APIs.
* Added Aperture solver except for MacOS.
* Added CoreTrail solver.
* Fixed some ValueError issues when comparin out of domain.

Version 1.2.3
-------------

Highlights
~~~~~~~~~~

* Fixed comparison operators that could evaluate to ``True`` or ``False`` instead of a model constraint.
* Unsupported comparisons now raise clear errors.
* Added numeric PB ordering comparisons.

Version 1.2.2
----------------

Highlights
~~~~~~~~~~

* Fixed soundness issues in mixed Boolean/``IntVar`` comparisons and Big-M constraints with negated indicators.

Version 1.2.1
-------------

Highlights
~~~~~~~~~~

* Disabled preprocessing for UWrMaxSATCompetition due to crashes.
* Disabled CGSS PMRES due to soudnness issues.
* Started incorporating MaxSATRegressionSuite: https://github.com/tobipaxe/MaxSATRegressionSuite/tree/main
* Fixed ``IntVector.all_different`` off by one error (not a soudness isseu, but could raise an error preventing a valid model from solving).
* Moved SoftRef soft registration and updates under ``m.obj``.
* Improved the form ``X + Y <= Z + c`` fast path with a better encoding.
* Refined Big-M bool sum cases.
* Improved ``IntVar == sum(unit-bools)`` with a count ladder builder.
* Reduced formula size in ``IntVar + bool-sum`` fast path.
* Improved ``sum_var()`` for mixed integer widths.
* Improved ``cumulative(..., backend="auto")`` backend selection and overhead.
* Fixed ``IntSetVar.contains(IntVar)`` on upper bounds.
* Fixed expression decoding that could inject new vars.
* Raise on non nullable enums with empty choice domains.
* Fixed ``IntVector[IntVar]`` to use absolute index values.
* Fixed routing for ``IntSetVar`` algebra operations.
* Fixed incremental routing for certain constraints.
* Stopped ``IntSetVar`` algebra ops from mutating model too early.
* Added decoding for multiplexer and index integer element expressions.
* Fixed ``IntSetVector.is_in(...)`` for set-valued rows.
* Added ``EnumVar.is_in_or_none(...)`` for nullable enum subset checks.
* Deferred ``IntSetVar != ...`` and ``IntVector != IntVector`` until commit.
* Improved internal helper memoization.
* Improved encoding of ``IntSetVar.contains(IntVar)``.
* Improved ``sum_expr(...)`` performance.
* Improved performance of ``ClauseGroup.extend(..., inplace=True)`` and ``Clause.append(..., inplace=True)``.
* Improved performance of ``PBExpr.add/sub(..., inplace=True)``.
* Improved performance of ``m.obj.add(...)``.
* Registered implied AMO/EO structure from cardinalities for usage of PB(AMO).
* Switched enum domains to ``seqcounter`` (pairwise up to 8).



Version 1.2.0
-------------

Highlights
~~~~~~~~~~

* Reimplementesd GMTO to follow original PB(AMO) paper closely.
* Safer and more efficient PB(AMO) default auto-routing.
* More efficient constraint merging in Model, specially when PB(AMO) auto-routing is involved.
* Added MaxHS and iMaxHS support.
* Heavily simplified all solver wrappers with inheritance.

Version 1.1.1
-------------

Highlights
~~~~~~~~~~

* Added :class:`hermax.non_incremental.incomplete.TTOpenWBOInc`, a subprocess-isolated wrapper around the TT Open-WBO-Inc variant.
* New encoder API :mod:`hermax.encoder`.
* New PBAMO / structured pseudo-Boolean encoder support.
* Broader modeling-layer coverage for typed collections, element constraints,
  sets, and integer expressions.
* Integer modeling domains now use closed bounds ``[lb, ub]`` instead of half-open bounds ``[lb, ub)``.
* Better export/solve convenience and more examples in the docs.

Encoder API
~~~~~~~~~~~

* Added the :doc:`encoder_api` reference page.
* Added :doc:`encoder_pbamo` for PBAMO and structured PB encoders.
* Exposed the encoder package from Python as ``hermax.encoder``.

Structured PB / PBAMO
~~~~~~~~~~~~~~~~~~~~~

Pseudo-Boolean support was significantly expanded.

* Added PBAMO-backed structured PB encoders.
* Added documented encoder families including GGPW, GMTO, GSWC, MDD, and RGGT.
* Added overlap-aware structured PB compilation examples and tests.

Modeling Layer
~~~~~~~~~~~~~~

* Improved support for typed vectors and collections.
* Added clearer support for variable-index element constraints.
* Expanded set-oriented modeling helpers and examples.
* Broadened integer-expression coverage, including more aggregate and relation
  cases.
* Added more cumulative and scheduling-oriented regression coverage.
