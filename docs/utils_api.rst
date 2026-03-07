Utilities API
=============

The :mod:`hermax.utils` module exposes small, solver-agnostic helpers that are
useful across modelling, testing, and experimentation. At the moment it
contains pure-Python sorting network utilities (Batcher's odd-even merge sort
networks [1]_ [2]_) and helper functions to apply them to Python sequences.

Sorting Networks
----------------

The exported API provides two representations:

* a flat comparator list (:class:`hermax.utils.SortingNetwork`)
* a dependency-safe layered representation (:class:`hermax.utils.SortingNetworkLayers`)

Both are generated for a requested width ``n`` and support arbitrary ``n >= 1``
by building the next power-of-two Batcher network and pruning comparators that
would touch padded wires.

.. autofunction:: hermax.utils.batcher_odd_even_sorting_network

.. autofunction:: hermax.utils.batcher_odd_even_sorting_network_layers

.. autofunction:: hermax.utils.apply_sorting_network

.. autofunction:: hermax.utils.apply_sorting_network_layers

.. autoclass:: hermax.utils.SortingNetwork
   :members:
   :undoc-members:

.. autoclass:: hermax.utils.SortingNetworkLayers
   :members:
   :undoc-members:

References
----------

.. [1] Kenneth E. Batcher. *Sorting networks and their applications*. Proceedings of the April 30--May 2, 1968, Spring Joint Computer Conference, pp. 307-314, 1968.
.. [2] Donald E. Knuth. *The Art of Computer Programming, Volume 3: Sorting and Searching*. Addison-Wesley Professional, 1998.
