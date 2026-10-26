Objective API migration (1.3)
============================

Use the following replacements:

.. list-table::
   :header-rows: 1
   :widths: 48 52

   * - Previous usage
     - Replacement
   * - ``m.obj[w] += expression`` (numeric cost)
     - ``m.obj += w * expression``
   * - ``m.obj[w] += literal`` (Boolean preference)
     - ``m.obj += w * ~literal``
   * - ``m.tier_obj[t, w] += expression`` (numeric cost)
     - ``m.tier_obj.add(expression, weight=w, tier=t)``
   * - ``m.tier_obj[t, w] += literal`` (Boolean preference)
     - ``m.tier_obj.add(~literal, weight=w, tier=t)``
   * - ``ref = m.obj.add_soft(expression, w)`` (numeric cost)
     - ``ref = m.obj.add(expression, weight=w)``
   * - ``ref = m.obj.add_soft(literal, w)`` (Boolean preference)
     - ``ref = m.obj.add(~literal, weight=w)``
   * - ``m.obj.update_soft(ref, w)``
     - ``m.obj.update(ref, weight=w)``
   * - ``m.update_soft_weight(ref, w)``
     - ``m.obj.update(ref, weight=w)``

Weighted indexing and numeric ``add_soft`` inputs now raise ``TypeError``.
Boolean ``add_soft`` and the old weight-update methods remain available with
``FutureWarning`` during the transition.

For a compound Boolean preference:

.. code-block:: python

   # Before
   m.obj[w] += condition

   # After
   satisfied = m.bool()
   m &= condition.iff(satisfied)
   m.obj += w * ~satisfied

``obj.add()`` now returns a handle. Replace chained additions with separate
``obj += expression`` statements. Change a handle's weight with
``obj.update(ref, weight=w)``.

``obj.set()`` now replaces the entire objective. Use ``obj += expression`` to
append costs. Configure decimal precision before adding numeric costs, or
clear the objective before changing it. Precision changes invalidate legacy
preference handles.

Numeric assignment, including ``m.obj = route_cost(distances)``, is unchanged.
