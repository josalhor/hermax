Changelog
=========

Version 1.2.1
-------------

Highlights
~~~~~~~~~~

* Disabled preprocessing for UWrMaxSATCompetition due to crashes.
* Disabled CGSS PMRES due to soudnness issues.
* Started incorporating MaxSATRegressionSuite: https://github.com/tobipaxe/MaxSATRegressionSuite/tree/main
* Fixed ``IntVector.all_different`` off by one error (not a soudness isseu, but could raise an error preventing a valid model from solving).
* Simplified ``update_soft_weight(ref, ...)`` SoftRef API description.
* Improved the form ``X + Y <= Z + c`` fast path with a better encoding.
* Refined Big-M bool sum cases.
* Improved ``IntVar == sum(unit-bools)`` with a count ladder builder.
* Reduced formula size in ``IntVar + bool-sum`` fast path.



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
