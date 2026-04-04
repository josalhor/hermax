#!/usr/bin/env python
# -*- coding:utf-8 -*-
##
# rc2.py
##
# Created on: Dec 2, 2017
# Author: Alexey S. Ignatiev
# E-mail: aignatiev@ciencias.ulisboa.pt
##

"""
    ===============
    List of classes
    ===============

    .. autosummary::
        :nosignatures:

        RC2
        RC2Stratified

    ==================
    Module description
    ==================

    An implementation of the RC2 algorithm for solving maximum
    satisfiability. RC2 stands for *relaxable cardinality constraints*
    (alternatively, *soft cardinality constraints*) and represents an
    improved version of the OLLITI algorithm, which was described in
    [1]_ and [2]_ and originally implemented in the `MSCG MaxSAT
    solver <https://reason.di.fc.ul.pt/wiki/doku.php?id=mscg>`_.

    Initially, this solver was supposed to serve as an example of a possible
    PySAT usage illustrating how a state-of-the-art MaxSAT algorithm could be
    implemented in Python and still be efficient. It participated in the
    `MaxSAT Evaluations 2018
    <https://maxsat-evaluations.github.io/2018/rankings.html>`_ and `2019
    <https://maxsat-evaluations.github.io/2019/rankings.html>`_ where,
    surprisingly, it was ranked first in two complete categories: *unweighted*
    and *weighted*. A brief solver description can be found in [3]_. A more
    detailed solver description can be found in [4]_.

    .. [1] António Morgado, Carmine Dodaro, Joao Marques-Silva.
        *Core-Guided MaxSAT with Soft Cardinality Constraints*. CP
        2014. pp. 564-573

    .. [2] António Morgado, Alexey Ignatiev, Joao Marques-Silva.
        *MSCG: Robust Core-Guided MaxSAT Solving*. JSAT 9. 2014.
        pp. 129-134

    .. [3] Alexey Ignatiev, António Morgado, Joao Marques-Silva.
        *RC2: A Python-based MaxSAT Solver*. MaxSAT Evaluation 2018.
        p. 22

    .. [4] Alexey Ignatiev, António Morgado, Joao Marques-Silva.
        *RC2: An Efficient MaxSAT Solver*. MaxSAT Evaluation 2018.
        JSAT 11. 2019. pp. 53-64

    The file implements two classes: :class:`RC2` and
    :class:`RC2Stratified`. The former class is the basic
    implementation of the algorithm, which can be applied to a MaxSAT
    formula in the :class:`.WCNF` format. The latter class
    additionally implements Boolean lexicographic optimization (BLO)
    [5]_ and stratification [6]_ on top of :class:`RC2`.

    .. [5] Joao Marques-Silva, Josep Argelich, Ana Graça, Inês Lynce.
        *Boolean lexicographic optimization: algorithms &
        applications*. Ann. Math. Artif. Intell. 62(3-4). 2011.
        pp. 317-343

    .. [6] Carlos Ansótegui, Maria Luisa Bonet, Joel Gabàs, Jordi
        Levy. *Improving WPM2 for (Weighted) Partial MaxSAT*. CP
        2013. pp. 117-132

    The implementation can be used as an executable (the list of
    available command-line options can be shown using ``rc2.py -h``)
    in the following way:

    ::

        $ xzcat formula.wcnf.xz
        p wcnf 3 6 4
        1 1 0
        1 2 0
        1 3 0
        4 -1 -2 0
        4 -1 -3 0
        4 -2 -3 0

        $ rc2.py -vv formula.wcnf.xz
        c formula: 3 vars, 3 hard, 3 soft
        c cost: 1; core sz: 2; soft sz: 2
        c cost: 2; core sz: 2; soft sz: 1
        s OPTIMUM FOUND
        o 2
        v -1 -2 3
        c oracle time: 0.0001

    Alternatively, the algorithm can be accessed and invoked through the
    standard ``import`` interface of Python, e.g.

    .. code-block:: python

        >>> from pysat.examples.rc2 import RC2
        >>> from pysat.formula import WCNF
        >>>
        >>> wcnf = WCNF(from_file='formula.wcnf.xz')
        >>>
        >>> with RC2(wcnf) as rc2:
        ...     for m in rc2.enumerate():
        ...         print('model {0} has cost {1}'.format(m, rc2.cost))
        model [-1, -2, 3] has cost 2
        model [1, -2, -3] has cost 2
        model [-1, 2, -3] has cost 2
        model [-1, -2, -3] has cost 3

    As can be seen in the example above, the solver can be instructed
    either to compute one MaxSAT solution of an input formula, or to
    enumerate a given number (or *all*) of its top MaxSAT solutions.

    ==============
    Module details
    ==============
"""

#
# ==============================================================================
from __future__ import print_function
import cProfile
import pstats
import collections
import getopt
import itertools
from math import copysign
import os
from pysat.formula import CNFPlus, WCNFPlus
from pysat.card import ITotalizer
from pysat.solvers import Solver, SolverNames
import re
import six
from six.moves import range
import sys
import random
try:
    from pysat.maxpre import preprocess_formula
except Exception:
    def preprocess_formula(formula, *args, **kwargs):
        return formula
try:
    from pyprooflogger import VeriPbProoflogger, MaxSATProoflogger, TotalizerProoflogger
except Exception:
    class _NoOpProoflogger:
        def __init__(self, *args, **kwargs):
            pass

    VeriPbProoflogger = _NoOpProoflogger
    MaxSATProoflogger = _NoOpProoflogger
    TotalizerProoflogger = _NoOpProoflogger


#
# ==============================================================================
class RC2(object):
    """
        Implementation of the basic RC2 algorithm. Given a (weighted)
        (partial) CNF formula, i.e. formula in the :class:`.WCNF`
        format, this class can be used to compute a given number of
        MaxSAT solutions for the input formula. :class:`RC2` roughly
        follows the implementation of algorithm OLLITI [1]_ [2]_ of
        MSCG and applies a few heuristics on top of it. These include

        - *unsatisfiable core exhaustion* (see method :func:`exhaust_core`),
        - *unsatisfiable core reduction* (see method :func:`minimize_core`),
        - *intrinsic AtMost1 constraints* (see method :func:`adapt_am1`).

        :class:`RC2` can use any SAT solver available in PySAT. The
        default SAT solver to use is ``g3`` (see
        :class:`.SolverNames`). Additionally, if Glucose is chosen,
        the ``incr`` parameter controls whether to use the incremental
        mode of Glucose [7]_ (turned off by default). Boolean
        parameters ``adapt``, ``exhaust``, and ``minz`` control
        whether or to apply detection and adaptation of intrinsic
        AtMost1 constraints, core exhaustion, and core reduction.
        Unsatisfiable cores can be trimmed if the ``trim`` parameter
        is set to a non-zero integer. Finally, verbosity level can be
        set using the ``verbose`` parameter.

        .. [7] Gilles Audemard, Jean-Marie Lagniez, Laurent Simon.
            *Improving Glucose for Incremental SAT Solving with
            Assumptions: Application to MUS Extraction*. SAT 2013.
            pp. 309-317

        :param formula: (weighted) (partial) CNF formula
        :param solver: SAT oracle name
        :param adapt: detect and adapt intrinsic AtMost1 constraints
        :param exhaust: do core exhaustion
        :param incr: use incremental mode of Glucose
        :param minz: do heuristic core reduction
        :param trim: do core trimming at most this number of times
        :param verbose: verbosity level

        :type formula: :class:`.WCNF`
        :type solver: str
        :type adapt: bool
        :type exhaust: bool
        :type incr: bool
        :type minz: bool
        :type trim: int
        :type verbose: int
    """

    def __init__(self, formula, solver='g3', adapt=False, exhaust=False, incr=False, minz=False,
                 trim=0, verbose=0, add_cores=0, speed_up_assumps=0, verification_solver=None, clone=False, prooflogger=None, maxsat_prooflogger=None, totalizer_prooflogger=None):
        """
            Constructor.
        """
        # saving verbosity level and other options
        self.verbose = verbose
        self.exhaust = exhaust
        self.solver = solver
        self.adapt = adapt
        self.minz = minz
        self.trim = trim
        self.add_cores = add_cores
        self.speed_up_assumps_strategy = speed_up_assumps
        self.clone = clone
        self.verification_solver = None
        self.prooflogger = prooflogger
        self.maxsat_prooflogger = maxsat_prooflogger
        self.totalizer_prooflogger = totalizer_prooflogger

        if verification_solver:
            self.verification_solver = Solver(
                name=verification_solver, bootstrap_with=formula.hard, incr=incr, use_timer=False)
            if not self.verification_solver:
                print("c initiating verification solver",
                      verification_solver, "failed.")
                exit(0)
            else:
                print("c using verification solver", verification_solver)

        # clause selectors and mapping from selectors to clause ids
        self.selectors, self.selectors_map, self.all_selectors, self.selectors_to_clause, self.sneg = [], {}, [], {}, set([
        ])

        # other MaxSAT related stuff
        self.topv = formula.nv
        # The constant that should be added to the objective function
        self.objective_constant = 0
        self.weights = {}  # weights of soft clauses
        self.sums = []  # totalizer sum assumptions, This are the currently active counting variables
        self.totalizer_bounds = {}  # a mapping from sum assumptions to totalizer bounds
        self.totalizer_objects = {}  # a mapping from sum assumptions to totalizer objects
        self.swgt = {}  # a mapping from sum assumptions to their core weights
        self.cost = 0

        # save original sels and weights
        # used if the cost of model is calculated (rc2_wce does it if upper bounds are used)
        self.selectors_orig = []
        self.weights_orig = {}

        # set for selectors that should no longer be considered for this level but not removed
        self.selectors_to_deactivate = set()
        # set for counter variables that should no longer be considered for this level but not removed
        self.sums_to_deactivate = set()

        # stats
        self.stats_iters = 0
        self.stats_cores = 0
        self.stats_coresize_sum = 0
        self.stats_coresizes = []
        self.stats_corecosts = []
        self.stats_assumpssize_sum = 0
        self.stats_assumpssizes = []
        self.stats_sums = []
        self.stats_sum_variables = {}

        # mappings between internal and external variables
        VariableMap = collections.namedtuple('VariableMap', ['e2i', 'i2e'])
        self.vmap = VariableMap(e2i={}, i2e={})

        # initialize SAT oracle with hard clauses only
        self.init(formula, incr=incr)

        # PROOF: Initializing prooflogger constraints
        if self.prooflogger:
            self.prooflogger.write_comment(
                "Init base objective reformulation constraint")
            self.proof_base_reform = self.prooflogger.rup_constraint([], 0)
            self.proof_model_improve = None

        # PROOF: Objective should be known at this point
        if self.prooflogger:
            self.prooflogger.set_objective(
                [-l for l in list(self.weights.keys())], list(self.weights.values()), self.objective_constant)
            self.prooflogger.write_comment_objective_function()
        # core minimization is going to be extremely expensive
        # for large plain formulas, and so we turn it off here
        weight_values = self.weights.values()
        if not formula.hard and len(self.selectors) > 100000 and min(weight_values) == max(weight_values):
            self.minz = False

    def __del__(self):
        """
            Destructor.
        """
        self.delete()

    def __enter__(self):
        """
            'with' constructor.
        """
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """
            'with' destructor.
        """
        self.delete()

    def init(self, formula, incr=False):
        """
            Initialize the internal SAT oracle. The oracle is used
            incrementally and so it is initialized only once when
            constructing an object of class :class:`RC2`. Given an
            input :class:`.WCNF` formula, the method bootstraps the
            oracle with its hard clauses. It also augments the soft
            clauses with "fresh" selectors and adds them to the oracle
            afterwards.

            Optional input parameter ``incr`` (``False`` by default)
            regulates whether or not Glucose's incremental mode [7]_
            is turned on.

            :param formula: input formula
            :param incr: apply incremental mode of Glucose

            :type formula: :class:`.WCNF`
            :type incr: bool
        """

        # creating a solver object
        self.oracle = Solver(
            name=self.solver,
            bootstrap_with=formula.hard,
            incr=incr,
            use_timer=True,
        )

        if self.solver in SolverNames.glucose3:
            if hasattr(self.oracle, "speed_up_assumps"):
                self.oracle.speed_up_assumps(self.speed_up_assumps_strategy)

        if hasattr(SolverNames, "minisatpbc") and self.solver in SolverNames.minisatpbc:
            self.oracle.solver.set_pbc_opts(self.pbc_opts)

        # adding native cardinality constraints (if any) as hard clauses
        # this can be done only if the Minicard solver is in use
        # this cannot be done if RC2 is run from the command line
        if isinstance(formula, WCNFPlus) and formula.atms:
            assert self.solver in SolverNames.minicard, \
                'Only Minicard supports native cardinality constraints. Make sure you use the right type of formula.'

            for atm in formula.atms:
                self.oracle.add_atmost(*atm)

        self.UB = 1  # upper bound for cost. not needed here, but RC2WCE can use this, so it is easiest to calculate here. Initial value is larger than the largest possible cost: thus 1

        # adding soft clauses to oracle
        for i, cl in enumerate(formula.soft):
            selv = cl[0]  # if clause is unit, selector variable is its literal

            if len(cl) > 1:
                self.topv += 1
                selv = self.topv

                # PROOF: Add meaningful name for the blocking variables to match interpretation in VeriPB
                if self.prooflogger:
                    self.maxsat_prooflogger.add_blocking_literal_for_var(
                        self.topv, formula.soft_constraint_idx[i], True)

                self.selectors_to_clause[selv] = cl[:]
                cl.append(-self.topv)
                self.oracle.add_clause(cl)

                if self.verification_solver:
                    self.verification_solver.add_clause(cl)

            self.UB += formula.wght[i]

            if selv in self.weights:
                self.weights[selv] += formula.wght[i]
                self.weights_orig[selv] += formula.wght[i]
            elif -selv in self.weights:
                if self.weights[-selv] > formula.wght[i]:
                    self.objective_constant += formula.wght[i]
                    self.cost += formula.wght[i]
                    self.weights[-selv] -= formula.wght[i]
                    self.weights_orig[-selv] -= formula.wght[i]
                else:
                    self.objective_constant += self.weights[-selv]
                    self.cost += self.weights[-selv]

                    self.weights[selv] = formula.wght[i] - self.weights[-selv]
                    del self.weights[-selv]
                    self.weights_orig[selv] = formula.wght[i] - \
                        self.weights_orig[-selv]
                    del self.weights_orig[-selv]

                    self.selectors.remove(-selv)
                    self.selectors.append(selv)
                    del self.selectors_map[-selv]
                    self.selectors_map[selv] = i
                    self.selectors_orig.remove(-selv)
                    self.selectors_orig.append(selv)
            else:
                # record selector and its weight
                self.selectors.append(selv)
                self.weights[selv] = formula.wght[i]
                self.selectors_map[selv] = i

                self.selectors_orig.append(selv)
                self.weights_orig[selv] = formula.wght[i]

        # storing the set of selectors
        self.selectors_set = set(self.selectors)
        self.all_selectors = self.selectors[:]

        # at this point internal and external variables are the same
        for v in range(1, formula.nv + 1):
            self.vmap.e2i[v] = v
            self.vmap.i2e[v] = v

        if self.verbose > 1:
            print('c formula: {0} vars, {1} hard, {2} soft'.format(formula.nv,
                                                                   len(formula.hard), len(formula.soft)))

    def add_clause(self, clause, weight=None):
        """
            The method for adding a new hard of soft clause to the
            problem formula. Although the input formula is to be
            specified as an argument of the constructor of
            :class:`RC2`, adding clauses may be helpful when
            *enumerating* MaxSAT solutions of the formula. This way,
            the clauses are added incrementally, i.e. *on the fly*.

            The clause to add can be any iterable over integer
            literals. The additional integer parameter ``weight`` can
            be set to meaning the the clause being added is soft
            having the corresponding weight (note that parameter
            ``weight`` is set to ``None`` by default meaning that the
            clause is hard).

            :param clause: a clause to add
            :param weight: weight of the clause (if any)

            :type clause: iterable(int)
            :type weight: int

            .. code-block:: python

                >>> from pysat.examples.rc2 import RC2
                >>> from pysat.formula import WCNF
                >>>
                >>> wcnf = WCNF()
                >>> wcnf.append([-1, -2])  # adding hard clauses
                >>> wcnf.append([-1, -3])
                >>>
                >>> wcnf.append([1], weight=1)  # adding soft clauses
                >>> wcnf.append([2], weight=1)
                >>> wcnf.append([3], weight=1)
                >>>
                >>> with RC2(wcnf) as rc2:
                ...     rc2.compute()  # solving the MaxSAT problem
                [-1, 2, 3]
                ...     print(rc2.cost)
                1
                ...     rc2.add_clause([-2, -3])  # adding one more hard clause
                ...     rc2.compute()  # computing another model
                [-1, -2, 3]
                ...     print(rc2.cost)
                2
        """
        # first, map external literals to internal literals
        # introduce new variables if necessary
        cl = list(map(lambda l: self._map_extlit(l), clause if not len(
            clause) == 2 or not type(clause[0]) == list else clause[0]))

        if not weight:
            if not len(clause) == 2 or not type(clause[0]) == list:
                # the clause is hard, and so we simply add it to the SAT oracle
                self.oracle.add_clause(cl)
                if self.verification_solver:
                    self.verification_solver.add_clause(cl)
            else:
                # this should be a native cardinality constraint,
                # which can be used only together with Minicard
                assert self.solver in SolverNames.minicard, \
                    'Only Minicard supports native cardinality constraints.'

                self.oracle.add_atmost(cl, clause[1])
        else:
            # soft clauses should be augmented with a selector
            selv = cl[0]  # for a unit clause, no selector is needed

            if len(cl) > 1:
                self.topv += 1
                selv = self.topv

                self.selectors_to_clause[selv] = cl[:]
                cl.append(-self.topv)
                self.oracle.add_clause(cl)
                if self.verification_solver:
                    self.verification_solver.add_clause(cl)

            if selv not in self.weights:
                # record selector and its weight
                self.selectors.append(selv)
                self.weights[selv] = weight
                self.selectors_map[selv] = len(self.selectors) - 1
            else:
                # selector is not new; increment its weight
                self.weights[selv] += weight

            self.all_selectors.append(selv)
            self.selectors_set.add(selv)

    def delete(self):
        """
            Explicit destructor of the internal SAT oracle and all the
            totalizer objects creating during the solving process.
        """

        if hasattr(self, "oracle") and self.oracle:
            self.oracle.delete()
            self.oracle = None

            if self.solver not in SolverNames.minicard:  # for minicard, there is nothing to free
                for totalizer in six.itervalues(self.totalizer_objects):
                    totalizer.delete()

    def compute(self):
        """
            This method can be used for computing one MaxSAT solution,
            i.e. for computing an assignment satisfying all hard
            clauses of the input formula and maximizing the sum of
            weights of satisfied soft clauses. It is a wrapper for the
            internal :func:`compute_` method, which does the job,
            followed by the model extraction.

            Note that the method returns ``None`` if no MaxSAT model
            exists. The method can be called multiple times, each
            being followed by blocking the last model. This way one
            can enumerate top-:math:`k` MaxSAT solutions (this can
            also be done by calling :meth:`enumerate()`).

            :returns: a MaxSAT model
            :rtype: list(int)

            .. code-block:: python

                >>> from pysat.examples.rc2 import RC2
                >>> from pysat.formula import WCNF
                >>>
                >>> rc2 = RC2(WCNF())  # passing an empty WCNF() formula
                >>> rc2.add_clause([-1, -2])
                >>> rc2.add_clause([-1, -3])
                >>> rc2.add_clause([-2, -3])
                >>>
                >>> rc2.add_clause([1], weight=1)
                >>> rc2.add_clause([2], weight=1)
                >>> rc2.add_clause([3], weight=1)
                >>>
                >>> model = rc2.compute()
                >>> print(model)
                [-1, -2, 3]
                >>> print(rc2.cost)
                2
                >>> rc2.delete()
        """
        # simply apply MaxSAT only once
        res = self.compute_()

        if res:
            # extracting a model
            self.model = self.oracle.get_model()
            self.model = filter(lambda l: abs(l) in self.vmap.i2e, self.model)
            self.model = map(lambda l: int(
                copysign(self.vmap.i2e[abs(l)], l)), self.model)
            self.model = sorted(self.model, key=lambda l: abs(l))

            return self.model

    def enumerate(self, block=0):
        """
            Enumerate top MaxSAT solutions (from best to worst). The
            method works as a generator, which iteratively calls
            :meth:`compute` to compute a MaxSAT model, blocks it
            internally and returns it.

            An optional parameter can be used to enforce computation of MaxSAT
            models corresponding to different maximal satisfiable subsets
            (MSSes) or minimal correction subsets (MCSes). To block MSSes, one
            should set the ``block`` parameter to ``1``. To block MCSes, set
            it to ``-1``. By the default (for blocking MaxSAT models),
            ``block`` is set to ``0``.

            :param block: preferred way to block solutions when enumerating
            :type block: int

            :returns: a MaxSAT model
            :rtype: list(int)

            .. code-block:: python

                >>> from pysat.examples.rc2 import RC2
                >>> from pysat.formula import WCNF
                >>>
                >>> rc2 = RC2(WCNF())  # passing an empty WCNF() formula
                >>> rc2.add_clause([-1, -2])  # adding clauses "on the fly"
                >>> rc2.add_clause([-1, -3])
                >>> rc2.add_clause([-2, -3])
                >>>
                >>> rc2.add_clause([1], weight=1)
                >>> rc2.add_clause([2], weight=1)
                >>> rc2.add_clause([3], weight=1)
                >>>
                >>> for model in rc2.enumerate():
                ...     print(model, rc2.cost)
                [-1, -2, 3] 2
                [1, -2, -3] 2
                [-1, 2, -3] 2
                [-1, -2, -3] 3
                >>> rc2.delete()
        """
        done = False
        while not done:
            model = self.compute()

            if model != None:
                if block == 1:
                    # to block an MSS corresponding to the model, we add
                    # a clause enforcing at least one of the MSS clauses
                    # to be falsified next time
                    m, cl = set(self.oracle.get_model()), []

                    for selector_variable in self.all_selectors:
                        if selector_variable in m:
                            # clause is satisfied
                            cl.append(-selector_variable)

                            # next time we want to falsify one of these
                            # clauses, i.e. we should encode the negation
                            # of each of these selectors
                            if selector_variable in self.selectors_to_clause and not selector_variable in self.sneg:
                                self.sneg.add(selector_variable)
                                for il in self.selectors_to_clause[selector_variable]:
                                    self.oracle.add_clause(
                                        [selector_variable, -il])
                                if self.verification_solver:
                                    for il in self.selectors_to_clause[selector_variable]:
                                        self.verification_solver.add_clause(
                                            [selector_variable, -il])
                    self.oracle.add_clause(cl)
                    if self.verification_solver:
                        self.verification_solver.add_clause(cl)
                elif block == -1:
                    # a similar (but simpler) piece of code goes here,
                    # to block the MCS corresponding to the model
                    # (this blocking is stronger than MSS blocking above)
                    m = set(self.oracle.get_model())
                    self.oracle.add_clause(
                        [l for l in filter(lambda l: -l in m, self.all_selectors)])
                    if self.verification_solver:
                        self.verification_solver.add_clause(
                            [l for l in filter(lambda l: -l in m, self.all_selectors)])
                else:
                    # clauses added to the solver, need to be proven via rup before adding them. This clause is a RUP-clause with respect to the model improving constraint.
                    # here, we simply block a previous MaxSAT model
                    if not self.prooflogger:
                        self.add_clause([-l for l in model])

                yield model
            else:
                done = True

    def compute_(self):
        """
            Main core-guided loop, which iteratively calls a SAT
            oracle, extracts a new unsatisfiable core and processes
            it. The loop finishes as soon as a satisfiable formula is
            obtained. If specified in the command line, the method
            additionally calls :meth:`adapt_am1` to detect and adapt
            intrinsic AtMost1 constraints before executing the loop.

            :rtype: bool
        """
        # trying to adapt (simplify) the formula
        # by detecting and using atmost1 constraints
        if self.adapt:
            self.adapt_am1()

        # main solving loop
        # extract cores as long as we are UNSAT using the assumptions
        while not self.oracle.solve(assumptions=self.selectors + self.sums):
            self.stats_iters += 1
            self.stats_assumpssizes.append(
                len(self.selectors)+len(self.sums))
            self.stats_assumpssize_sum += len(
                self.selectors)+len(self.sums)

            self.get_core()

            # PROOF: The core received at this point is already logged
            # It is to late to assume here that the core is implied by RUP, as constraint that implied that core by RUP could be deleted

            if not self.core:
                # core is empty, i.e. hard part is unsatisfiable
                return False
            if self.verification_solver:
                if self.verification_solver.solve(assumptions=self.core):
                    print("VERIFICATION SOLVER GAVE DIFFERENT RESULT, CORE NOT CORE!")
                    exit(0)

            self.stats_cores += 1
            self.stats_coresizes.append(len(self.core))
            self.stats_corecosts.append(self.core_minweight)
            self.stats_coresize_sum += len(self.core)

            if len(self.core) < self.add_cores:
                self.oracle.add_clause([-l for l in self.core])
                if self.verification_solver:
                    self.verification_solver.add_clause(
                        [-l for l in self.core])
            elif len(self.core) < -self.add_cores:
                self.oracle.add_clause_as_learnt([-l for l in self.core])
                if self.verification_solver:
                    self.verification_solver.add_clause(
                        [-l for l in self.core])

            self.process_core()

            if self.verbose > 1:
                print('c cost: {0}; core sz: {1}; soft sz: {2}'.format(self.cost,
                                                                       len(self.core), len(self.selectors) + len(self.sums)))

        if self.prooflogger:
            self.prooflogger.write_comment("Log solution if better")
            model = self.oracle.get_model()
            self.proof_model_improve = self.prooflogger.log_solution_with_check(
                model)

        if self.verification_solver:
            if not self.verification_solver.solve(assumptions=self.selectors + self.sums):
                print(
                    "VERIFICATION SOLVER GAVE DIFFERENT RESULT, SATISFIABLE INSTANCE NOT SATISFIABLE!")
                exit(0)

        self.stats_iters += 1
        self.stats_coresizes.append(0)
        self.stats_corecosts.append(0)
        self.stats_assumpssizes.append(
            len(self.selectors)+len(self.sums))
        self.stats_assumpssize_sum += len(
            self.selectors)+len(self.sums)
        return True

    def get_core(self):
        """
            Extract unsatisfiable core. The result of the procedure is
            stored in variable ``self.core``. If necessary, core
            trimming and also heuristic core reduction is applied
            depending on the command-line options. A *minimum weight*
            of the core is computed and stored in ``self.core_minweight``.
            Finally, the core is divided into two parts:

            1. clause selectors (``self.core_selectors``),
            2. sum assumptions (``self.core_sums``).
        """

        # extracting the core
        self.core = self.oracle.get_core()

        # PROOF: Core is implied by RUP
        if self.prooflogger:
            self.prooflogger.write_comment("Log core")
            self.core_id = self.prooflogger.rup_constraint(
                [-l for l in self.core], 1)
            if len(self.core) < self.add_cores or len(self.core) == 1:
                self.prooflogger.move_to_core(-1)

        if self.core:
            # try to reduce the core by trimming
            self.trim_core()

            # and by heuristic minimization
            self.minimize_core()

            # the core may be empty after core minimization
            if not self.core:
                return

            # core weight
            self.core_minweight = min(
                map(lambda l: self.weights[l], self.core))

            # dividing the core into two parts
            iter1, iter2 = itertools.tee(self.core)
            self.core_selectors = list(
                l for l in iter1 if l in self.selectors_set)
            self.core_sums = list(
                l for l in iter2 if l not in self.selectors_set)

    def process_core(self):
        """
            The method deals with a core found previously in
            :func:`get_core`. Clause selectors ``self.core_selectors`` and
            sum assumptions involved in the core are treated
            separately of each other. This is handled by calling
            methods :func:`process_sels` and :func:`process_sums`,
            respectively. Whenever necessary, both methods relax the
            core literals, which is followed by creating a new
            totalizer object encoding the sum of the new relaxation
            variables. The totalizer object can be "exhausted"
            depending on the option.
        """

        self.prooflogger.write_comment("Process Core")

        # assumptions to remove
        self.garbage = set()

        # updating the cost
        self.cost += self.core_minweight

        if len(self.core_selectors) != 1 or len(self.core_sums) > 0:
            self.process_selectors()
            # process previously introducded sums in the core
            self.process_sums()

            if len(self.relaxation_vars) > 1:
                # create a new cardinality constraint
                totalizer = self.create_sum()
                self.stats_sums.append(totalizer)

                # apply core exhaustion if required
                bound = self.exhaust_core(totalizer) if self.exhaust else 1
                if bound:
                    # save the info about this sum and
                    # add its assumption literal
                    self.set_bound(totalizer, bound, self.core_minweight)
                else:
                    # impossible to satisfy any of these clauses
                    # they must become hard
                    for relv in self.relaxation_vars:
                        self.oracle.add_clause([relv])
                    if self.verification_solver:
                        for relv in self.relaxation_vars:
                            self.verification_solver.add_clause([relv])

            else:
                self.oracle.add_clause([self.relaxation_vars[0]])
                if self.verification_solver:
                    self.verification_solver.add_clause(
                        [self.relaxation_vars[0]])
        else:
            # unit cores are treated differently
            # (their negation is added to the hard part)
            self.oracle.add_clause([-self.core_selectors[0]])
            if self.verification_solver:
                self.verification_solver.add_clause([-self.core_selectors[0]])
            self.garbage.add(self.core_selectors[0])

        # remove unnecessary assumptions
        self.filter_assumps()

    def adapt_am1(self):
        """
            Detect and adapt intrinsic AtMost1 constraints. Assume
            there is a subset of soft clauses
            :math:`\\mathcal{S}'\\subseteq \\mathcal{S}` s.t.
            :math:`\\sum_{c\\in\\mathcal{S}'}{c\\leq 1}`, i.e. at most
            one of the clauses of :math:`\\mathcal{S}'` can be
            satisfied.

            Each AtMost1 relationship between the soft clauses can be
            detected in the following way. The method traverses all
            soft clauses of the formula one by one, sets one
            respective selector literal to true and checks whether
            some other soft clauses are forced to be false. This is
            checked by testing if selectors for other soft clauses are
            unit-propagated to be false. Note that this method for
            detection of AtMost1 constraints is *incomplete*, because
            in general unit propagation does not suffice to test
            whether or not :math:`\\mathcal{F}\\wedge l_i\\models
            \\neg{l_j}`.

            Each intrinsic AtMost1 constraint detected this way is
            handled by calling :func:`process_am1`.
        """

        # literal connections
        conns = collections.defaultdict(lambda: set([]))
        confl = []

        # prepare connections
        for l1 in self.selectors:
            st, props = self.oracle.propagate(assumptions=[l1], phase_saving=2)
            if st:
                for l2 in props:
                    if -l2 in self.selectors_set:
                        conns[l1].add(-l2)
                        conns[-l2].add(l1)
            else:
                # propagating this literal results in a conflict
                confl.append(l1)

        if confl:  # filtering out unnecessary connections
            ccopy = {}
            confl = set(confl)

            for l in conns:
                if l not in confl:
                    cc = conns[l].difference(confl)
                    if cc:
                        ccopy[l] = cc

            conns = ccopy
            confl = list(confl)

            # processing unit size cores
            for l in confl:
                self.core, self.core_minweight = [l], self.weights[l]
                self.core_selectors, self.core_sums = [l], []
                self.process_core()

            if self.verbose > 1:
                print('c unit cores found: {0}; cost: {1}'.format(len(confl),
                                                                  self.cost))

        nof_am1 = 0
        len_am1 = []
        lits = set(conns.keys())
        while lits:
            am1 = [min(lits, key=lambda l: len(conns[l]))]

            for l in sorted(conns[am1[0]], key=lambda l: len(conns[l])):
                if l in lits:
                    for l_added in am1[1:]:
                        if l_added not in conns[l]:
                            break
                    else:
                        am1.append(l)

            # updating remaining lits and connections
            lits.difference_update(set(am1))
            for l in conns:
                conns[l] = conns[l].difference(set(am1))

            if len(am1) > 1:
                # treat the new atmost1 relation
                self.process_am1(am1)
                nof_am1 += 1
                len_am1.append(len(am1))

        # updating the set of selectors
        self.selectors_set = set(self.selectors)

        if self.verbose > 1 and nof_am1:
            print('c am1s found: {0}; avgsz: {1:.1f}; cost: {2}'.format(nof_am1,
                                                                        sum(len_am1) / float(nof_am1), self.cost))

    def process_am1(self, am1):
        """
            Process an AtMost1 relation detected by :func:`adapt_am1`.
            Note that given a set of soft clauses
            :math:`\\mathcal{S}'` at most one of which can be
            satisfied, one can immediately conclude that the formula
            has cost at least :math:`|\\mathcal{S}'|-1` (assuming
            *unweighted* MaxSAT). Furthermore, it is safe to replace
            all clauses of :math:`\\mathcal{S}'` with a single soft
            clause :math:`\\sum_{c\\in\\mathcal{S}'}{c}`.

            Here, input parameter ``am1`` plays the role of subset
            :math:`\\mathcal{S}'` mentioned above. The procedure bumps
            the MaxSAT cost by ``self.core_minweight * (len(am1) - 1)``.

            All soft clauses involved in ``am1`` are replaced by a
            single soft clause, which is a disjunction of the
            selectors of clauses in ``am1``. The weight of the new
            soft clause is set to ``self.core_minweight``.

            :param am1: a list of selectors connected by an AtMost1 constraint

            :type am1: list(int)
        """

        # computing am1's weight
        self.core_minweight = min(map(lambda l: self.weights[l], am1))

        # pretending am1 to be a core, and the bound is its size - 1
        self.core_selectors, b = am1, len(am1) - 1

        # incrementing the cost
        self.cost += b * self.core_minweight

        # assumptions to remove
        self.garbage = set()

        # splitting and relaxing if needed
        self.process_selectors()

        # new selector
        self.topv += 1
        am1_selector = self.topv

        # PROOF: Reify the variable representing the AM1 constraint and argue AM1 constraint
        if self.prooflogger:
            self.prooflogger.write_comment("Derive intrinsic AM1 constraint")
            self.proof_base_reform = self.maxsat_prooflogger.proof_log_at_most_one(
                self.proof_base_reform, self.relaxation_vars, am1_selector, self.core_minweight)

        self.oracle.add_clause(
            [-l for l in self.relaxation_vars] + [-am1_selector])
        if self.verification_solver:
            self.verification_solver.add_clause(
                [-l for l in self.relaxation_vars] + [-am1_selector])

        # integrating the new selector
        self.selectors.append(am1_selector)
        self.weights[am1_selector] = self.core_minweight
        self.selectors_map[am1_selector] = len(self.weights) - 1

        # removing unnecessary assumptions
        self.filter_assumps()

    def trim_core(self):
        """
            This method trims a previously extracted unsatisfiable
            core at most a given number of times. If a fixed point is
            reached before that, the method returns.
        """

        for i in range(self.trim):
            # call solver with core assumption only
            # it must return 'unsatisfiable'
            # PROOF: -> No proof logging of solution needed
            self.oracle.solve(assumptions=self.core)

            # extract a new core
            new_core = self.oracle.get_core()

            if len(new_core) == len(self.core):
                # PROOF: log that trimmed core is implied by RUP
                if self.prooflogger:
                    self.prooflogger.write_comment("Trimmed core")
                    temp_id = self.prooflogger.rup_constraint(
                        [-l for l in self.core], 1)
                    if self.core_id:
                        if len(self.core) < self.add_cores or len(self.core) == 1:
                            self.prooflogger.move_to_core(-1)
                        # self.prooflogger.delete_constraint(self.core_id)
                    self.core_id = temp_id

                # stop if new core is not better than the previous one
                break

            # otherwise, update core
            self.core = new_core

    def minimize_core(self):
        """
            Reduce a previously extracted core and compute an
            over-approximation of an MUS. This is done using the
            simple deletion-based MUS extraction algorithm.

            The idea is to try to deactivate soft clauses of the
            unsatisfiable core one by one while checking if the
            remaining soft clauses together with the hard part of the
            formula are unsatisfiable. Clauses that are necessary for
            preserving unsatisfiability comprise an MUS of the input
            formula (it is contained in the given unsatisfiable core)
            and are reported as a result of the procedure.

            During this core minimization procedure, all SAT calls are
            dropped after obtaining 1000 conflicts.
        """

        if self.minz and len(self.core) > 1:
            self.core = sorted(self.core, key=lambda l: self.weights[l])
            self.oracle.conf_budget(1000)

            i = 0
            while i < len(self.core):
                to_test = self.core[:i] + self.core[(i + 1):]

                # PROOF: RC2 should never terminate because of this satisfiable assignment
                if self.oracle.solve_limited(assumptions=to_test) == False:
                    self.core = to_test

                    # PROOF: log that minimised core is implied by RUP
                    if self.prooflogger:
                        self.prooflogger.write_comment("Minised core")
                        temp_id = self.prooflogger.rup_constraint(
                            [-l for l in self.core], 1)
                        if self.core_id:
                            if len(self.core) < self.add_cores or len(self.core) == 1:
                                self.prooflogger.move_to_core(-1)
                            self.prooflogger.delete_constraint(self.core_id)
                        self.core_id = temp_id
                else:
                    i += 1

    def exhaust_core(self, totalizer_obj):
        """
            Exhaust core by increasing its bound as much as possible.
            Core exhaustion was originally referred to as *cover
            optimization* in [6]_.

            Given a totalizer object ``totalizer_obj`` representing a sum of
            some *relaxation* variables :math:`r\\in R` that augment
            soft clauses :math:`\\mathcal{C}_r`, the idea is to
            increase the right-hand side of the sum (which is equal to
            1 by default) as much as possible, reaching a value
            :math:`k` s.t. formula
            :math:`\\mathcal{H}\\wedge\\mathcal{C}_r\\wedge(\\sum_{r\\in
            R}{r\\leq k})` is still unsatisfiable while increasing it
            further makes the formula satisfiable (here
            :math:`\\mathcal{H}` denotes the hard part of the
            formula).

            The rationale is that calling an oracle incrementally on a
            series of slightly modified formulas focusing only on the
            recently computed unsatisfiable core and disregarding the
            rest of the formula may be practically effective.
        """

        # the first case is simpler
        if self.oracle.solve(assumptions=[-totalizer_obj.rhs[1]]):
            if self.prooflogger:
                self.prooflogger.write_comment("Log solution if better")
                model = self.oracle.get_model()
                self.proof_model_improve = self.prooflogger.log_solution_with_check(
                    model)
            return 1
        else:
            self.cost += self.core_minweight

        for i in range(2, len(self.relaxation_vars)):
            # saving the previous bound
            self.totalizer_objects[-totalizer_obj.rhs[i - 1]] = totalizer_obj
            self.totalizer_bounds[-totalizer_obj.rhs[i - 1]] = i - 1

            # increasing the bound
            self.update_sum(-totalizer_obj.rhs[i - 1])

            if self.oracle.solve(assumptions=[-totalizer_obj.rhs[i]]):
                if self.prooflogger:
                    self.prooflogger.write_comment("Log solution if better")
                    model = self.oracle.get_model()
                    self.proof_model_improve = self.prooflogger.log_solution_with_check(
                        model)
                # the bound should be equal to i
                return i

            # the cost should increase further
            self.cost += self.core_minweight

        return None

    def process_selectors(self):
        """
            Process soft clause selectors participating in a new core.
            The negation :math:`\\neg{s}` of each selector literal
            :math:`s` participating in the unsatisfiable core is added
            to the list of relaxation literals, which will be later
            used to create a new totalizer object in
            :func:`create_sum`.

            If the weight associated with a selector is equal to the
            minimal weight of the core, e.g. ``self.core_minweight``, the
            selector is marked as garbage and will be removed in
            :func:`filter_assumps`. Otherwise, the clause is split as
            described in [1]_.
        """

        # new relaxation variables
        self.relaxation_vars = []
        for l in self.core_selectors:

            if self.weights[l] == self.core_minweight:
                self.garbage.add(l)
                self.relaxation_vars.append(-l)
            else:
                self.weights[l] -= self.core_minweight
                if self.clone:
                    self.topv += 1
                    # PROOF: variables are cloned
                    if self.prooflogger:
                        self.prooflogger.write_comment("Variable cloning")
                        self.prooflogger.redundancy_based_stregthening(
                            [l, self.topv], 1, self.topv)
                    self.oracle.add_clause([l, self.topv])
                    if self.verification_solver:
                        self.verification_solver.add_clause([l, self.topv])

                    self.relaxation_vars.append(self.topv)
                else:
                    self.relaxation_vars.append(-l)

    def process_sum(self, lit):
        totalizer, bound = self.update_sum(lit)

        # updating bounds and weights
        if bound < len(totalizer.rhs):
            lnew = -totalizer.rhs[bound]
            if lnew not in self.swgt:
                self.set_bound(totalizer, bound, self.swgt[lit])

    def process_sums(self):
        """
            Process cardinality sums participating in a new core.
            Whenever necessary, some of the sum assumptions are
            removed or split (depending on the value of
            ``self.core_minweight``). Deleted sums are marked as garbage and are
            dealt with in :func:`filter_assumps`.

            In some cases, the process involves updating the
            right-hand sides of the existing cardinality sums (see the
            call to :func:`update_sum`). The overall procedure is
            detailed in [1]_.
        """

        for l in self.core_sums:
            self.relaxation_vars.append(-l)

            if self.weights[l] == self.core_minweight:
                self.garbage.add(l)
            else:
                self.weights[l] -= self.core_minweight

            self.process_sum(l)

    def create_sum(self, bound=1):
        """
            Create a totalizer object encoding a cardinality
            constraint on the new list of relaxation literals obtained
            in :func:`process_sels` and :func:`process_sums`. The
            clauses encoding the sum of the relaxation literals are
            added to the SAT oracle. The sum of the totalizer object
            is encoded up to the value of the input parameter
            ``bound``, which is set to ``1`` by default.

            :param bound: right-hand side for the sum to be created
            :type bound: int

            :rtype: :class:`.ITotalizer`

            Note that if Minicard is used as a SAT oracle, native
            cardinality constraints are used instead of
            :class:`.ITotalizer`.
        """

        if self.solver not in SolverNames.minicard:  # standard totalizer-based encoding
            totalizer = ITotalizer(
                lits=self.relaxation_vars, ubound=bound, top_id=self.topv)

            # updating top variable id
            self.topv = totalizer.top_id

            # adding its clauses to oracle
            for cl in totalizer.cnf.clauses:
                self.oracle.add_clause(cl)
            if self.verification_solver:
                for cl in totalizer.cnf.clauses:
                    self.verification_solver.add_clause(cl)
        else:
            # for minicard, use native cardinality constraints instead of the
            # standard totalizer, i.e. create a new (empty) totalizer sum and
            # fill it with the necessary data supported by minicard
            totalizer = ITotalizer()
            totalizer.lits = self.relaxation_vars

            self.topv += 1  # a new variable will represent the bound

            # proper initial bound
            totalizer.rhs = [None] * (len(totalizer.lits))
            totalizer.rhs[bound] = self.topv

            # new atmostb constraint instrumented with
            # an implication and represented natively
            rhs = len(totalizer.lits)
            amb = [[-self.topv] * (rhs - bound) + totalizer.lits, rhs]

            # add constraint to the solver
            self.oracle.add_atmost(*amb)

        return totalizer

    def update_sum(self, assump):
        """
            The method is used to increase the bound for a given
            totalizer sum. The totalizer object is identified by the
            input parameter ``assump``, which is an assumption literal
            associated with the totalizer object.

            The method increases the bound for the totalizer sum,
            which involves adding the corresponding new clauses to the
            internal SAT oracle.

            The method returns the totalizer object followed by the
            new bound obtained.

            :param assump: assumption literal associated with the sum
            :type assump: int

            :rtype: :class:`.ITotalizer`, int

            Note that if Minicard is used as a SAT oracle, native
            cardinality constraints are used instead of
            :class:`.ITotalizer`.
        """

        # getting a totalizer object corresponding to assumption
        totalizer = self.totalizer_objects[assump]

        # increment the current bound
        bound = self.totalizer_bounds[assump] + 1

        if self.solver not in SolverNames.minicard:  # the case of standard totalizer encoding
            # increasing its bound
            totalizer.increase(ubound=bound, top_id=self.topv)

            # updating top variable id
            self.topv = totalizer.top_id

            # adding its clauses to oracle
            if totalizer.nof_new:
                for cl in totalizer.cnf.clauses[-totalizer.nof_new:]:
                    self.oracle.add_clause(cl)
                if self.verification_solver:
                    for cl in totalizer.cnf.clauses[-totalizer.nof_new:]:
                        self.verification_solver.add_clause(cl)

        else:  # the case of cardinality constraints represented natively
            # right-hand side is always equal to the number of input literals
            rhs = len(totalizer.lits)

            if bound < rhs:
                # creating an additional bound
                if not totalizer.rhs[bound]:
                    self.topv += 1
                    totalizer.rhs[bound] = self.topv

                # a new at-most-b constraint
                amb = [[-totalizer.rhs[bound]] *
                       (rhs - bound) + totalizer.lits, rhs]
                self.oracle.add_atmost(*amb)

        return totalizer, bound

    def set_bound(self, totalizer, rhs, weight):
        """
            Given a totalizer sum and its right-hand side to be
            enforced, the method creates a new sum assumption literal,
            which will be used in the following SAT oracle calls.

            :param tobj: totalizer sum
            :param rhs: right-hand side

            :type tobj: :class:`.ITotalizer`
            :type rhs: int
        """

        # saving the sum and its weight in a mapping
        self.totalizer_objects[-totalizer.rhs[rhs]] = totalizer
        self.totalizer_bounds[-totalizer.rhs[rhs]] = rhs
        self.weights[-totalizer.rhs[rhs]] = weight
        self.swgt[-totalizer.rhs[rhs]] = weight

        # adding a new assumption to force the sum to be at most rhs
        self.sums.append(-totalizer.rhs[rhs])

    def filter_assumps(self):
        """
            Filter out unnecessary selectors and sums from the list of
            assumption literals. The corresponding values are also
            removed from the dictionaries of bounds and weights.

            Note that assumptions marked as garbage are collected in
            the core processing methods, i.e. in :func:`process_core`,
            :func:`process_sels`, and :func:`process_sums`.
        """

        self.selectors = list(
            filter(lambda x: x not in self.garbage, self.selectors))
        self.sums = list(filter(lambda x: x not in self.garbage, self.sums))

        self.totalizer_bounds = {l: b for l, b in six.iteritems(
            self.totalizer_bounds) if l not in self.garbage}
        self.weights = {l: w for l, w in six.iteritems(
            self.weights) if l not in self.garbage}

        self.selectors_set.difference_update(set(self.garbage))

        self.garbage.clear()

    def oracle_time(self):
        """
            Report the total SAT solving time.
        """
        return self.oracle.time_accum()

    def _map_extlit(self, l):
        """
            Map an external variable to an internal one if necessary.

            This method is used when new clauses are added to the
            formula incrementally, which may result in introducing new
            variables clashing with the previously used *clause
            selectors*. The method makes sure no clash occurs, i.e. it
            maps the original variables used in the new problem
            clauses to the newly introduced auxiliary variables (see
            :func:`add_clause`).

            Given an integer literal, a fresh literal is returned. The
            returned integer has the same sign as the input literal.

            :param l: literal to map
            :type l: int

            :rtype: int
        """
        v = abs(l)

        if v in self.vmap.e2i:
            return int(copysign(self.vmap.e2i[v], l))
        else:
            self.topv += 1

            self.vmap.e2i[v] = self.topv
            self.vmap.i2e[self.topv] = v

            return int(copysign(self.topv, l))

    def print_stats(self):
        b = "c SOLVER-STATS"
        if self.oracle:
            self.oracle.print_stats()

        print(b, "iters:", self.stats_iters)
        print(b, "cores:", self.stats_cores)
        print(b, "coresizes[]:", self.stats_coresizes)
        print(b, "corecosts[]:", self.stats_corecosts)
        print(b, "coresize_sum:", self.stats_coresize_sum)
        print(b, "assumpssizes[]:", self.stats_assumpssizes)
        print(b, "assumpssize_sum:", self.stats_assumpssize_sum)
        print(b, "sums_rhss[]:", [len(i.rhs) for i in self.stats_sums])
        print(b, "sums_nof_lits[]:", [len(i.lits) for i in self.stats_sums])

#
# ==============================================================================


class RC2Stratified(RC2, object):
    """
        RC2 augmented with BLO and stratification techniques. Although
        class :class:`RC2` can deal with weighted formulas, there are
        situations when it is necessary to apply additional heuristics
        to improve the performance of the solver on weighted MaxSAT
        formulas. This class extends capabilities of :class:`RC2` with
        two heuristics, namely

        1. Boolean lexicographic optimization (BLO) [5]_
        2. stratification [6]_

        There is no way to enable only one of them -- both heuristics
        are applied at the same time. Except for the aforementioned
        additional techniques, every other component of the solver
        remains as in the base class :class:`RC2`. Therefore, a user
        is referred to the documentation of :class:`RC2` for details.
    """

    def __init__(self, formula, solver='g3', adapt=False, exhaust=False, incr=False, minz=False,
                 nohard=False, trim=0, verbose=0, add_cores=0, speed_up_assumps=0, verification_solver=None, clone=False, prooflogger=None, maxsat_prooflogger=None, totalizer_prooflogger=None):
        """
            Constructor.
        """

        # calling the constructor for the basic version
        super(RC2Stratified, self).__init__(formula, solver=solver, adapt=adapt, exhaust=exhaust, incr=incr, minz=minz, trim=trim,
                                            verbose=verbose, add_cores=add_cores, speed_up_assumps=speed_up_assumps, verification_solver=verification_solver, clone=clone, prooflogger=prooflogger, maxsat_prooflogger=maxsat_prooflogger, totalizer_prooflogger=totalizer_prooflogger)

        self.levl = 0   # initial optimization level
        self.blop = []  # a list of blo levels

        # do clause hardening
        self.hard = nohard == False

        # backing up selectors
        self.bckp, self.bckp_set = self.selectors, self.selectors_set
        self.selectors = []

        # initialize Boolean lexicographic optimization
        self.init_wstr()

    def init_wstr(self):
        """
            Compute and initialize optimization levels for BLO and
            stratification. This method is invoked once, from the
            constructor of an object of :class:`RC2Stratified`. Given
            the weights of the soft clauses, the method divides the
            MaxSAT problem into several optimization levels.
        """

        # a mapping for stratified problem solving,
        # i.e. from a weight to a list of selectors
        self.wstr = collections.defaultdict(lambda: [])

        for s, w in six.iteritems(self.weights):
            self.wstr[w].append(s)

        # sorted list of distinct weight levels
        self.blop = sorted([w for w in self.wstr], reverse=True)

        # diversity parameter for stratification
        self.sdiv = len(self.blop) / 2.0

        # number of finished levels
        self.done = 0

    def compute(self):
        """
            This method solves the MaxSAT problem iteratively. Each
            optimization level is tackled the standard way, i.e. by
            calling :func:`compute_`. A new level is started by
            calling :func:`next_level` and finished by calling
            :func:`finish_level`. Each new optimization level
            activates more soft clauses by invoking
            :func:`activate_clauses`.
        """

        if self.done == 0:
            # it is a fresh start of the solver
            # i.e. no optimization level is finished yet
            # first attempt to get an optimization level
            self.next_level()

            while self.levl != None and self.done < len(self.blop):
                # add more clauses
                self.done = self.activate_clauses(self.done)

                if self.verbose > 1:
                    print('c wght str:', self.blop[self.levl])

                # call RC2
                if self.compute_() == False:
                    return

                # updating the list of distinct weight levels
                self.blop = sorted([w for w in self.wstr], reverse=True)

                if self.done < len(self.blop):
                    if self.verbose > 1:
                        print('c curr opt:', self.cost)

                    # done with this level
                    if self.hard:
                        # harden the clauses if necessary
                        self.finish_level()

                    self.levl += 1

                    # get another level
                    self.next_level()

                    if self.verbose > 1:
                        print('c')
        else:
            # we seem to be in the model enumeration mode
            # with the first model being already computed
            # i.e. all levels are finished and so all clauses are present
            # thus, we need to simply call RC2 for the next model
            self.done = -1  # we are done with stratification, disabling it
            if self.compute_() == False:
                return

        # extracting a model
        self.model = self.oracle.get_model()
        self.model = filter(lambda l: abs(l) in self.vmap.i2e, self.model)
        self.model = map(lambda l: int(
            copysign(self.vmap.i2e[abs(l)], l)), self.model)
        self.model = sorted(self.model, key=lambda l: abs(l))

        return self.model

    def next_level(self):
        """
            Compute the next optimization level (starting from the
            current one). The procedure represents a loop, each
            iteration of which checks whether or not one of the
            conditions holds:

            - partial BLO condition
            - stratification condition

            If any of these holds, the loop stops.
        """
        if self.levl >= len(self.blop):
            self.levl = None
            return

        while self.levl < len(self.blop) - 1:
            # number of selectors with weight less than current weight
            numc = sum([len(self.wstr[w])
                       for w in self.blop[(self.levl + 1):]])

            # sum of their weights
            sumw = sum([w * len(self.wstr[w])
                       for w in self.blop[(self.levl + 1):]])

            # partial BLO
            if self.blop[self.levl] > sumw and sumw != 0:
                break

            # stratification
            if numc / float(len(self.blop) - self.levl - 1) > self.sdiv:
                break

            self.levl += 1

    def activate_clauses(self, beg):
        """
            This method is used for activating the clauses that belong
            to optimization levels up to the newly computed level. It
            also reactivates previously deactivated clauses (see
            :func:`process_sels` and :func:`process_sums` for
            details).
        """
        end = min(self.levl + 1, len(self.blop))

        for l in range(beg, end):
            for sel in self.wstr[self.blop[l]]:
                if sel in self.bckp_set:
                    self.selectors.append(sel)
                else:
                    self.sums.append(sel)

        # updating set of selectors
        self.selectors_set = set(self.selectors)

        return end

    # PROOF: Here the hardening happens and the reformulated objective needs to be calculated to argue the hardening, reformulated objective only needed if we actually harden literals
    def finish_level(self):
        """
            This method does postprocessing of the current
            optimization level after it is solved. This includes
            *hardening* some of the soft clauses (depending on their
            remaining weights) and also garbage collection.
        """
        # assumptions to remove
        self.garbage = set()

        # sum of weights of the remaining levels
        sumw = sum([w * len(self.wstr[w])
                   for w in self.blop[(self.levl + 1):]])

        # trying to harden selectors and sums
        objective_reformulated = False
        for s in self.selectors + self.sums:
            if self.weights[s] > sumw:
                # PROOF: Log hardening
                if self.prooflogger:
                    self.prooflogger.write_comment("Log hardening of variable, since weight " + str(
                        self.weights[s]) + " bigger than sum of remaining weights " + str(sumw))
                    self.prooflogger.write_comment(
                        "Lower bound: " + str(self.cost))
                    self.prooflogger.write_comment(
                        "Upper bound: " + str(self.prooflogger.get_best_objective_value()))
                    if not objective_reformulated:
                        reformulated_objective = self.maxsat_prooflogger.proof_log_objective_reformulation(
                            self.proof_base_reform, self.proof_model_improve)
                        objective_reformulated = True
                    self.prooflogger.rup_constraint([s], 1)
                    self.prooflogger.move_to_core(-1)

                if self.prooflogger:
                    self.prooflogger.write_comment(
                        "Propagations following from hardening")
                self.oracle.add_clause([s])
                if self.verification_solver:
                    self.verification_solver.add_clause([s])
                self.garbage.add(s)

        # if objective_reformulated:
        #     self.prooflogger.delete_constraint(reformulated_objective)

        if self.verbose > 1:
            print('c hardened:', len(self.garbage))

        # remove unnecessary assumptions
        self.filter_assumps()

    def process_am1(self, am1):
        """
            Due to the solving process involving multiple optimization
            levels to be treated individually, new soft clauses for
            the detected intrinsic AtMost1 constraints should be
            remembered. The method is a slightly modified version of
            the base method :func:`RC2.process_am1` taking care of
            this.
        """
        # computing am1's weight
        self.core_minweight = min(map(lambda l: self.weights[l], am1))

        # pretending am1 to be a core, and the bound is its size - 1
        self.core_selectors, b = am1, len(am1) - 1

        # incrementing the cost
        self.cost += b * self.core_minweight

        # assumptions to remove
        self.garbage = set()

        # splitting and relaxing if needed
        self.process_selectors()

        # new selector
        self.topv += 1
        selv = self.topv

        # PROOF: Reify the variable representing the AM1 constraint and argue AM1 constraint
        if self.prooflogger:
            self.prooflogger.write_comment("Derive intrinsic AM1 constraint")
            self.proof_base_reform = self.maxsat_prooflogger.proof_log_at_most_one(
                self.proof_base_reform, self.relaxation_vars, selv, self.core_minweight)

        self.oracle.add_clause([-l for l in self.relaxation_vars] + [-selv])
        if self.verification_solver:
            self.verification_solver.add_clause(
                [-l for l in self.relaxation_vars] + [-selv])

        # integrating the new selector
        self.selectors.append(selv)
        self.weights[selv] = self.core_minweight
        self.selectors_map[selv] = len(self.weights) - 1

        # do not forget this newly selector!
        self.bckp_set.add(selv)

        # removing unnecessary assumptions
        self.filter_assumps()

    def process_selectors(self):
        """
            A redefined version of :func:`RC2.process_sels`. The only
            modification affects the clauses whose weight after
            splitting becomes less than the weight of the current
            optimization level. Such clauses are deactivated and to be
            reactivated at a later stage.
        """

        # new relaxation variables
        self.relaxation_vars = []

        # selectors that should be deactivated (but not removed completely)
        self.selectors_to_deactivate = set()

        for l in self.core_selectors:
            if self.weights[l] == self.core_minweight:
                self.garbage.add(l)
                self.relaxation_vars.append(-l)
            else:
                self.weights[l] -= self.core_minweight
                if self.done != -1 and self.weights[l] < self.blop[self.levl]:
                    self.wstr[self.weights[l]].append(l)
                    self.selectors_to_deactivate.add(l)

                if self.clone:
                    self.topv += 1
                    # PROOF: variables are cloned
                    if self.prooflogger:
                        self.prooflogger.write_comment("Variable cloning")
                        self.prooflogger.redundancy_based_stregthening(
                            [l, self.topv], 1, self.topv)
                    self.oracle.add_clause([l, self.topv])
                    if self.verification_solver:
                        self.verification_solver.add_clause([l, self.topv])

                    self.relaxation_vars.append(self.topv)
                else:
                    self.relaxation_vars.append(-l)
        # deactivating unnecessary selectors
        self.selectors = list(
            filter(lambda x: x not in self.selectors_to_deactivate, self.selectors))

    def process_sums(self):
        """
            A redefined version of :func:`RC2.process_sums`. The only
            modification affects the clauses whose weight after
            splitting becomes less than the weight of the current
            optimization level. Such clauses are deactivated and to be
            reactivated at a later stage.
        """

        # sums that should be deactivated (but not removed completely)
        self.sums_to_deactivate = set()

        for l in self.core_sums:
            self.relaxation_vars.append(-l)

            if self.weights[l] == self.core_minweight:
                # marking variable as being a part of the core
                # so that next time it is not used as an assump
                self.garbage.add(l)
            else:
                # do not remove this variable from assumps
                # since it has a remaining non-zero weight
                self.weights[l] -= self.core_minweight

                # deactivate this assumption and put at a lower level
                # if self.done != -1, i.e. if stratification is disabled
                if self.done != -1 and self.weights[l] < self.blop[self.levl]:
                    self.wstr[self.weights[l]].append(l)
                    self.sums_to_deactivate.add(l)

            self.process_sum(l)

        # deactivating unnecessary sums
        self.sums = list(
            filter(lambda x: x not in self.sums_to_deactivate, self.sums))


#
# ==============================================================================

def parse_options():
    """
        Parses command-line option
    """
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'ab:c:Cd:e:E:f:hilLmnNM:pPqQs:S:t:T:uvV:Wxo',
                                   ['adapt', 'block=', 'comp=', 'clone', 'add-cores=', 'enum=', 'eq-opts=', 'verification-solver=', 'help',
                                    'incr', 'blo', 'lower-bounds', 'minimize', 'no-structure-sharing', 'no-wce', 'maxpre=', 'print-stats', 'PMRES',
                                    'instant-quit', 'eq-tree', 'solver=', 'speed-up-assumps=', 'trim=', 'ss-options=', 'use-ub', 'verbose',
                                    'sdiv=', 'vnew', 'WCE', 'exhaust', 'old-format'])
    except getopt.GetoptError as err:
        sys.stderr.write(str(err).capitalize())
        usage()
        sys.exit(1)

    adapt = False
    block = 'model'
    cmode = None
    clone = False
    add_cores = 0
    to_enum = 1
    eq_options = None
    verification_solver = None
    incr = False
    blo = False
    minz = False
    maxpre = False
    structure_sharing_opts = (1, 8)
    no_wce = False
    print_stats = False
    pmres = False
    instant_quit = False
    eqtree = False
    solver = 'g3'
    speed_up_assumps_strategy = 0
    trim = 0
    structure_sharing_opts = (1, 8)
    use_ub = False
    verbose = 1
    sdivp = 2.0
    vnew = False
    WCE = False
    exhaust = False
    oldF = False

    for opt, arg in opts:
        if opt in ('-a', '--adapt'):
            adapt = True
        elif opt in ('-b', '--block'):
            block = str(arg)
        elif opt in ('-c', '--comp'):
            cmode = str(arg)
        elif opt in ('-C', '--clone'):
            clone = True
        elif opt in ('-d', '--add-cores'):
            add_cores = int(arg)
        elif opt in ('-e', '--enum'):
            to_enum = str(arg)
            if to_enum != 'all':
                to_enum = int(to_enum)
            else:
                to_enum = 0
        elif opt in ('-E', '--eq-opts'):
            eq_options = (int(arg.split(",")[0]), int(arg.split(",")[1]))
        elif opt in ('-f', '--verification-solver'):
            verification_solver = str(arg)
        elif opt in ('-h', '--help'):
            usage()
            sys.exit(0)
        elif opt in ('-i', '--incr'):
            incr = True
        elif opt in ('-l', '--blo'):
            blo = True
        elif opt in ('-m', '--minimize'):
            minz = True
        elif opt in ('-M', '--maxpre'):
            larg = arg.split(",")
            if len(larg) == 1:
                maxpre = (float(larg[0]), "[bu]#[buvsrgc]")
            else:
                maxpre = (float(larg[0]), larg[1])
            # maxpre = (1, "[bu]#[buvsrgc]")
        elif opt in ('-n', '--no-structure-sharing'):
            structure_sharing_opts = None
        elif opt in ('-N', '--no-wce'):
            no_wce = True
        elif opt in ('-p', '--print-stats'):
            print_stats = True
        elif opt in ('-P', '--PMRES'):
            pmres = True
        elif opt in ('-q', '--instant-quit'):
            instant_quit = True
        elif opt in ('-Q', '--eq-tree'):
            eqtree = True
        elif opt in ('-s', '--solver'):
            solver = str(arg)
        elif opt in ('-S', '--speed-up-assumps'):
            speed_up_assumps_strategy = int(arg)
        elif opt in ('-t', '--trim'):
            trim = int(arg)
        elif opt in ('-T', '--ss-options'):
            structure_sharing_opts = (
                int(arg.split(",")[0]), int(arg.split(",")[1]))
        elif opt in ('-u', '--use-ub'):
            use_ub = True
        elif opt in ('-v', '--verbose'):
            verbose += 1
        elif opt in ('-V', '--sdiv'):
            sdivp = float(arg)
        elif opt == '--vnew':
            vnew = True
        elif opt in ('-W', '--WCE'):
            WCE = True
        elif opt in ('-x', '--exhaust'):
            exhaust = True
        elif opt in ('-o', '--old-format'):
            oldF = True
        else:
            assert False, 'Unhandled option: {0} {1}'.format(opt, arg)

    bmap = {'mcs': -1, 'mcses': -1, 'model': 0,
            'models': 0, 'mss': 1, 'msses': 1}

    assert block in bmap, 'Unknown solution blocking'

    return adapt, block, cmode, add_cores, to_enum, eq_options, verification_solver, incr, blo, minz, maxpre, structure_sharing_opts, no_wce, print_stats, pmres, instant_quit, \
        eqtree, solver, speed_up_assumps_strategy, trim, structure_sharing_opts, use_ub, verbose, sdivp, vnew, WCE, exhaust, oldF, clone, args


#
# ==============================================================================
def usage():
    """
        Prints usage message.
    """
    print('Usage:', os.path.basename(
        sys.argv[0]), '[options] dimacs-file [proof-file]')
    print('Options:')
    print('        -a, --adapt               Try to adapt (simplify) input formula')
    print('        -b, --block=<string>      When enumerating MaxSAT models, how to block previous solutions')
    print('                                  Available values: mcs, model, mss (default = model)')
    print('        -c, --comp=<string>       Enable one of the MSE18 configurations')
    print('                                  Available values: a, b, none (default = none)')
    print('        -C, --clone               Enable clause cloning')
    print('        -d, --add-cores=<int>     Add found cores as hard clauses in the solver if core size is smaller than given constant')
    print('        -e, --enum=<int>          Number of MaxSAT models to compute')
    print(
        '                                  Available values: [1 .. INT_MAX], all (default = 1)')
    print('        -f, --verification-solver=<string> ')
    print('                                  For debugging, use another SAT-solver to verify SAT-solver cores and SATISFIABLE results!')
    print('        -h, --help                Show this message')
    print('        -i, --incr                Use SAT solver incrementally (only for g3 and g4)')
    print('        -l, --blo                 Use BLO and stratification')
    print('        -m, --minimize            Use a heuristic unsatisfiable core minimizer')
    print('        -M, --maxpre              Use maxpre preprocessing.')
    print('        -s, --solver=<string>     SAT solver to use')
    print('                                  Available values: g3, g4, lgl, mcb, mcm, mpl, m22, mc, mgh (default = g3)')
    print('        -S, --speed-up-assumps=<int> set speed up assumption based sat strategy, available only when solver is Glucose3')
    print('        -p, --stats               Print solver stats')
    print('        -q, --instant-quit        Do not run Max-SAT-algorithm')
    print('        -t, --trim=<int>          How many times to trim unsatisfiable cores')
    print(
        '                                  Available values: [0 .. INT_MAX] (default = 0)')
    print('        -v, --verbose             Be verbose')
    print('        --vnew                    Print v-line in the new format')
    print('        -W, --WCE                 Use WCE technique. Structure sharing tecnhique is also used, unless it is disabled by -n')
    print('        -x, --exhaust             Exhaust new unsatisfiable cores')
    print('        -o, --old-format          Parse WCNF files in pre 2022 format')
    print('')
    print('When WCE technique is used, following extra options are available:')
    print('        -E, --eq-opts=<int>,<int>    Add equivalences to totalizer partially. Parameters: add_eq_thresold, add_eq_max_cost')
    print('                                       Larger parameter values lead to more equivalences. Default: None (setting this parameter enables the technique)')
    print('        -n, --no-structure-sharing   Don\'t use structure sharing technique (by default is used)')
    print('        -N, --no-wce                 Don\'t use WCE technique (uses WCE code, enabling ss, but always goes to relax phase after a core)')
    print('        -P, --PMRES                  Use PMRES relaxing instead of OLL')
    print('        -Q, --eq-tree                Add equivalences in totalizer instead of implications.')
    print('        -T, --ss-options=<int>,<int> Options for structure sharing: reusing, thresold (default: 1,8)')
    print('        -u, --use-ub                 Use upper bounds so that search can possibly be terminated earlier')


#
# ==============================================================================


def main():
    adapt, block, cmode, add_cores, to_enum, eq_options, verification_solver, incr, blo, minz, maxpre, structure_sharing_opts, no_wce, print_stats, pmres, instant_quit, \
        eqtree, solver, speed_up_assumps, trim, structure_sharing_opts, use_ub, verbose, sdivp, vnew, WCE, exhaust, oldF, clone, files = parse_options()

    newForm = not oldF
    if files:
        # parsing the input formula
        if re.search('\\.wcnf[p|+]?(\\.(gz|bz2|lzma|xz))?$', files[0]):
            formula = WCNFPlus(from_file=files[0], newFormat=newForm)
        else:  # expecting '*.cnf[,p,+].*'
            formula = CNFPlus(from_file=files[0]).weighted()

        # initialize prooflogger if proof filename is given as option
        if len(files) >= 2:
            prooflogger = VeriPbProoflogger()
            maxsat_prooflogger = MaxSATProoflogger(prooflogger)
            totalizer_prooflogger = TotalizerProoflogger(prooflogger)
            prooflogger.init_proof_file(files[1])
            # PROOF: Write the proof header and initialise the prooflogger
            nbclause = len(formula.hard) + formula.number_non_unit_soft_clauses
            nbvariables = formula.nv + formula.number_non_unit_soft_clauses
            prooflogger.write_proof_header(nbclause, nbvariables)
        else:
            prooflogger = None
            maxsat_prooflogger = None
            totalizer_prooflogger = None

        if maxpre:
            # For now we do not have proof logging for MaxPre and warn the user that this is not proof logged
            if prooflogger:
                print(
                    "c Warning: MaxPre cannot be used at the same time! Preprocessing is not proof logged!")
            formula = preprocess_formula(
                formula, timelimit=maxpre[0], options=maxpre[1])

        if verbose:
            print("c Parsing done")
            print("c Variables: ", formula.nv)
            print("c Hard clauses: ", len(formula.hard))
            print("c Soft clauses: ", len(formula.soft))

        # enabling the competition mode
        if cmode:
            assert cmode in (
                'a', 'b'), 'Wrong MSE18 mode chosen: {0}'.format(cmode)
            adapt, blo, exhaust, solver, verbose = True, True, True, 'g3', 3

            if cmode == 'a':
                trim = 5 if max(formula.wght) > min(formula.wght) else 0
                minz = False
            else:
                trim, minz = 0, True

            # trying to use unbuffered standard output
            if sys.version_info.major == 2:
                sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

        # Initialize the solver object
        stratif = False
        if WCE:
            if blo and len(formula.wght) > 0 and max(formula.wght) > min(formula.wght):
                MXS = rc2_wce.RC2WCEStratified
            else:
                MXS = rc2_wce.RC2WCE
            rc2 = MXS(formula, solver=solver, adapt=adapt, exhaust=exhaust, incr=incr, minz=minz, eq_opts=eq_options, structure_sharing_opts=structure_sharing_opts,
                      no_wce=no_wce, trim=trim, verbose=verbose, add_cores=add_cores, eqtree=eqtree, use_upper_bounds=use_ub, speed_up_assumps=speed_up_assumps, sdivp=sdivp,
                      pmres=pmres, verification_solver=verification_solver, prooflogger=prooflogger, maxsat_prooflogger=maxsat_prooflogger, totalizer_prooflogger=totalizer_prooflogger)
        else:
            if blo and max(formula.wght) > min(formula.wght):
                MXS = RC2Stratified
            else:
                MXS = RC2
            rc2 = MXS(formula, solver=solver, adapt=adapt, exhaust=exhaust, incr=incr, minz=minz, trim=trim, verbose=verbose,
                      add_cores=add_cores, speed_up_assumps=speed_up_assumps, verification_solver=verification_solver, clone=clone, prooflogger=prooflogger, maxsat_prooflogger=maxsat_prooflogger, totalizer_prooflogger=totalizer_prooflogger)

        # Check why this exists
        if instant_quit:
            print('c INSTANT QUIT')
            if print_stats:
                rc2.print_stats()
            if prooflogger:
                prooflogger.end_proof()
            sys.exit(0)

        # disable clause hardening in case we enumerate multiple models
        if stratif and to_enum != 1:
            print('c hardening is disabled for model enumeration')
            rc2.hard = False

        # Proof logging for solution enumeration is not supported right now
        if to_enum > 1:
            print("c Warning: Proof logging for enumerating solutions is not supported!")

        optimum_found = False
        for i, model in enumerate(rc2.enumerate(block=block), 1):
            optimum_found = True

            if verbose:
                if print_stats:
                    rc2.print_stats()
                if i == 1:
                    # PROOF: Proof that the optimal solution is optimal
                    if rc2.prooflogger:
                        rc2.prooflogger.write_comment(
                            "Log that UB = LB, optimum found")
                        rc2.maxsat_prooflogger.derive_objective_reformulation_constraint(
                            rc2.proof_base_reform)
                        # rc2.prooflogger.rup_empty_clause()
                        rc2.prooflogger.write_previous_constraint_conclusion_bounds()

                    print('s OPTIMUM FOUND')
                    print('o {0}'.format(rc2.cost))

                if verbose > 2:
                    if vnew:  # new format of the v-line
                        print('v', ''.join(str(int(l > 0)) for l in model))
                    else:
                        print('v', ' '.join([str(l) for l in model]))

            if i == to_enum:
                break
        else:
            # needed for MSE'20
            if verbose > 2 and vnew and to_enum != 1 and block == 1:
                print('v')

        if verbose:
            if not optimum_found:
                print('s UNSATISFIABLE')
            elif to_enum != 1:
                print('c models found:', i)

            if verbose > 1:
                print('c oracle time: {0:.4f}'.format(rc2.oracle_time()))

        if prooflogger:
            prooflogger.end_proof()


if __name__ == '__main__':
    main()
    # profile = cProfile.Profile()
    # profile.runcall(main)
    # ps = pstats.Stats(profile)
    # ps.print_stats()
