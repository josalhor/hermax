Loading formula files
=====================

Use ``hermax.formula.load_formula`` to load a CNF or WCNF file, including
supported compressed files:

.. code-block:: python

   from hermax.formula import load_formula
   from hermax.incremental import CoreTrail

   formula = load_formula("problem.wcnf.gz")
   solver = CoreTrail(formula)
   solver.solve()

Hermax also accepts supported PySAT formula objects.
Use ``to_pysat()`` on an exported formula when a PySAT object is needed.
