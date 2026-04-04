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
import collections
import getopt
import itertools
from math import copysign
import os
from pysat.solvers import Solver, SolverNames
try:
    from pysat.card import SSEncoder  # available only in CGSS-custom pysat
except Exception:
    SSEncoder = None
import re
import six
from six.moves import range
import sys
import time

from . import rc2

# Helper
# ==============================================================================


def lit2var(lit):
    return abs(lit)

#
# ==============================================================================


class RC2WCE(rc2.RC2, object):
    """
        RC2 encanced with WCE
    """

    def __init__(self, formula, solver='g3', adapt=False, exhaust=False, incr=False, minz=False, eq_opts=None,
                 structure_sharing_opts=None, no_wce=False, trim=0, verbose=0, add_cores=0, eqtree=False, use_upper_bounds=False,
                 speed_up_assumps=0, sdivp=2.0, pmres=False, verification_solver=None, prooflogger=None, maxsat_prooflogger=None, totalizer_prooflogger=None):
        """
            Constructor.
        """

        # calling the constructor for the basic version
        super(RC2WCE, self).__init__(formula, solver=solver, adapt=adapt, exhaust=exhaust, incr=incr, minz=minz, trim=trim,
                                     verbose=verbose, add_cores=add_cores, speed_up_assumps=speed_up_assumps, verification_solver=verification_solver, prooflogger=prooflogger, maxsat_prooflogger=maxsat_prooflogger, totalizer_prooflogger=totalizer_prooflogger)

        self.add_partial_equivalences = False
        self.eqtree = eqtree
        self.add_eq_options = (0, 0)
        self.no_wce = no_wce
        if eq_opts:
            self.add_partial_equivalences = True
            self.add_eq_options = eq_opts

        if structure_sharing_opts:
            self.ss_separate_relax = False
            self.ss_options = structure_sharing_opts
            self.use_ss = True
        else:
            self.ss_separate_relax = True
            self.ss_options = (0, 1000000)
            self.use_ss = False

        self.use_upper_bounds = use_upper_bounds

        self.pmres = pmres
        if self.use_ss:
            if SSEncoder is None:
                raise RuntimeError("SSEncoder is unavailable in this pysat build")
            if self.prooflogger:
                self.ssenc = SSEncoder(self.ss_options[0], self.ss_options[1], None,
                                       pmres, self.add_eq_options[0], self.add_eq_options[1], self.eqtree, with_proof=True, veriPB_PL=self.prooflogger, totalizer_PL=self.totalizer_prooflogger)
            else:
                self.ssenc = SSEncoder(self.ss_options[0], self.ss_options[1], None,
                                       pmres, self.add_eq_options[0], self.add_eq_options[1], self.eqtree)

        self.wcores = []

        self.stats_wce_coresizes = []
        self.stats_wce_assumpssizes = []
        self.stats_wce_cores = []
        self._time_wcores = 0.0
        self._time_satsolver = 0.0

    def delete(self):
        """
            Explicit destructor of the internal SAT oracle and all the
            totalizer objects creating during the solving process.
        """
        super(RC2WCE, self).delete()

    def compute(self):
        """
            The changes made to rc2 compute: use of upper bounds
        """
        # simply apply MaxSAT only once
        res = self.compute_()

        if res:
            # extracting a model
            if self.cost == self.UB:
                self.model = self.best_model
            else:
                self.model = self.oracle.get_model()

            if not self.model:  # UB==self.cost may cause that there is no model
                # TODO: what if model is actually wanted..?
                # TODO: is this currently handled by initing UB to be more than maximum possible cost?
                return None

            self.model = filter(lambda l: abs(l) in self.vmap.i2e, self.model)
            self.model = map(lambda l: int(
                copysign(self.vmap.i2e[abs(l)], l)), self.model)
            self.model = sorted(self.model, key=lambda l: abs(l))

            return self.model

    def compute_(self):
        """
            Changes made: WCE implemented
        """
        # trying to adapt (simplify) the formula
        # by detecting and using atmost1 constraints
        if self.adapt:
            # PROOF: proof logging of AM1 constraint here needed
            self.adapt_am1()

        # CHECK THIS
        if self.use_upper_bounds and self.cost == self.UB:
            print("c skip solving, self.cost==self.UB")
            return True

        # main solving loop
        while 1:
            self.stats_wce_coresizes.append([])
            self.stats_wce_assumpssizes.append([])
            a = time.time()
            while not self.oracle.solve(assumptions=self.selectors + self.sums):
                self._time_satsolver += time.time()-a
                self.stats_iters += 1
                self.stats_assumpssizes.append(
                    len(self.selectors)+len(self.sums))
                self.stats_wce_assumpssizes[-1].append(
                    len(self.selectors)+len(self.sums))
                self.stats_assumpssize_sum += len(
                    self.selectors)+len(self.sums)

                # A new core is found
                self.get_core()

                # PROOF: The core received at this point is already logged
                # It is to late to assume here that the core is implied by RUP, as constraint that implied that core by RUP could be deleted

                if not self.core:  # core is empty, i.e. hard part is unsatisfiable
                    return False
                if self.verification_solver:
                    if self.verification_solver.solve(assumptions=self.core):
                        print(
                            "VERIFICATION SOLVER GAVE DIFFERENT RESULT, CORE NOT CORE!")
                        exit(0)

                # Log some stats about the core
                self.stats_cores += 1
                self.stats_coresizes.append(len(self.core))
                self.stats_corecosts.append(self.core_minweight)
                self.stats_wce_coresizes[-1].append(len(self.core))
                self.stats_coresize_sum += len(self.core)

                # Decide if the core is added to the formula
                # If the parameter self.add_cores is positive, add cores smaller than self.add_cores as part of the formula
                if len(self.core) < self.add_cores:
                    self.oracle.add_clause([-l for l in self.core])
                    if self.verification_solver:
                        self.verification_solver.add_clause(
                            [-l for l in self.core])
                # If the parameter self.add_cores is negative, add cores smaller than -self.add_cores as a learnt clause
                elif len(self.core) < -self.add_cores:
                    self.oracle.add_clause_as_learnt([-l for l in self.core])
                    if self.verification_solver:
                        self.verification_solver.add_clause(
                            [-l for l in self.core])

                # Handles selectors of the core and adds core to list for processing later on if the core is not unit
                # Updates the cost (RC2 lower bound) with the weight of the core
                self.process_core()

                # PROOF: can terminate early if cost (RC lower bound) = upper bound. To prove this we can:
                # (1) Reformulate the objective with previously processed cores (including counter variables)
                # (2) Add not yet processed cores (without counter variables)
                # Do step (2) here by adding to base objective reformulation constraint; step (1) is taken care of in the main function (by further modifying the base objective reformulation constraint)
                if self.use_upper_bounds and self.cost == self.UB:
                    print("c no more cores needed, self.cost==self.UB")
                    # PROOF: Proof log step (2) by updating the base objective reformulation constraint
                    # We get the constraintIDs of the cores from the self.wcores, where the fifth parameter is the ID
                    if self.prooflogger:
                        self.prooflogger.write_comment(
                            "Add unprocessed cores to the objective reformulation constraint")
                        self.proof_base_reform = self.maxsat_prooflogger.reformulate_with_unprocessed_cores(
                            self.proof_base_reform, [core[4] for core in self.wcores], [core[3] for core in self.wcores])
                    return True

                if self.verbose > 1:
                    print('c cost: {0}; core sz: {1}; soft sz: {2}'.format(self.cost,
                                                                           len(self.core), len(self.selectors) + len(self.sums)))
                a = time.time()
                if self.no_wce and len(self.wcores):
                    break

            self._time_satsolver += time.time()-a

            # PROOF: Log solution
            # Since, the solver could terminate any time, we need to log any solution that is better than our incumbent solution.
            if self.prooflogger:
                self.prooflogger.write_comment("Log solution if better")
                model = self.oracle.get_model()
                if model:
                    self.proof_model_improve = self.prooflogger.log_solution_with_check(
                        model)

            if self.verification_solver:
                if not self.verification_solver.solve(assumptions=self.selectors + self.sums):
                    print(
                        "VERIFICATION SOLVER GAVE DIFFERENT RESULT, SATISFIABLE INSTANCE NOT SATISFIABLE!")
                    exit(0)

            # handle upper bound (This is already handled for the proof logging)
            if self.use_upper_bounds:
                model = self.oracle.get_model()
                if model:
                    mcost = self.objective_constant
                    for sel in self.selectors_orig:
                        if sel not in model:
                            mcost += self.weights_orig[sel]
                    if mcost < self.UB:
                        self.best_model = model
                        self.UB = mcost

                        # PROOF: can terminate early if cost (RC lower bound) = upper bound. To prove this we can:
                        # (1) Reformulate the objective with previously processed cores (including counter variables)
                        # (2) Add not yet processed cores (without counter variables)
                        # Do step (2) here by adding to base objective reformulation constraint; step (1) is taken care of in the main function (by further modifying the base objective reformulation constraint)
                        if self.cost == self.UB:
                            print("c final model found, self.cost==self.UB")
                            # PROOF: Proof log step (2) by updating the base objective reformulation constraint
                            # We get the constraintIDs of the cores from the self.wcores, where the fifth parameter is the ID
                            if self.prooflogger:
                                self.prooflogger.write_comment(
                                    "Add unprocessed cores to the objective reformulation constraint")
                                self.proof_base_reform = self.maxsat_prooflogger.reformulate_with_unprocessed_cores(
                                    self.proof_base_reform, [core[4] for core in self.wcores], [core[3] for core in self.wcores])
                            return True

                        if self.cost > self.UB:
                            print("c FAILLL")

            self.stats_wce_cores.append(len(self.wcores))
            if not self.process_wcores():
                break

        self.stats_iters += 1
        self.stats_coresizes.append(0)
        self.stats_corecosts.append(0)
        self.stats_assumpssizes.append(
            len(self.selectors)+len(self.sums))
        self.stats_assumpssize_sum += len(
            self.selectors)+len(self.sums)
        return True

    def ssenc_relax(self, cores):
        """
            relax array of cores using ssencoder
        """
        self.rcores = [i[0] for i in cores]
        new_outputs, new_clauses = self.ssenc.relax(
            self.rcores, top_id=self.topv)
        for cl in new_clauses:
            self.oracle.add_clause(cl)
        if self.verification_solver:
            for cl in new_clauses:
                self.verification_solver.add_clause(cl)
        self.topv = self.ssenc.top_id

        for i in range(len(cores)):
            if self.pmres:
                for nlit in new_outputs[i]:
                    lit = -nlit
                    if lit not in self.weights or not self.weights[lit]:
                        self.weights[lit] = cores[i][3]
                        self.sums.append(lit)
                    else:
                        self.weights[lit] += cores[i][3]

            else:
                # PROOF: Add core bounds to the MaxSAT prooflogger
                if self.prooflogger:
                    self.prooflogger.write_comment("Add core lower bound")
                    base_lit = new_outputs[i]
                    pb_def_id = self.totalizer_prooflogger.get_PbDef_invImpl_CxnId(
                        lit2var(base_lit))
                    self.maxsat_prooflogger.add_core_lower_bound(
                        lit2var(base_lit), cores[i][4], pb_def_id, cores[i][3])

                b, lit = self.exhaust_ssenc_core(
                    -new_outputs[i], cores[i][3]) if self.exhaust else (1, -new_outputs[i])
                if b:
                    if lit not in self.weights or not self.weights[lit]:
                        self.totalizer_bounds[lit] = b
                        self.weights[lit] = cores[i][3]
                        self.swgt[lit] = cores[i][3]
                        self.sums.append(lit)
                    else:
                        self.weights[lit] += cores[i][3]
                else:
                    # PROOF: If all output literals of the totalizer are true, then we can also set all input literals to true
                    if self.prooflogger:
                        self.prooflogger.write_comment(
                            "All totalizer outputs true -> all totalizer inputs true")
                    for relv in cores[i][0]:
                        if self.prooflogger:
                            self.prooflogger.rup_constraint([relv], 1)
                        self.oracle.add_clause([relv])
                    if self.verification_solver:
                        for relv in cores[i][0]:
                            self.verification_solver.add_clause([relv])

    def process_wcores(self):
        """
            process wce cores
            returns 0 if nothing to be done, otherwise 1
        """
        if len(self.wcores) == 0:
            return 0
        start_time = time.time()
        if self.use_ss and not self.ss_separate_relax:
            # structure sharing relax
            self.ssenc_relax(self.wcores)
        elif self.use_ss:
            # use ss encoder, but relax cores separately
            for i in self.wcores:
                self.ssenc_relax([i])
        else:
            # use "normal" totalizer TODO: currently use_ss is always true
            for i in self.wcores:
                self.relaxation_vars = i[0]
                self.core_selectors = i[1]
                self.core_sums = i[2]
                self.core_minweight = i[3]

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
        self.wcores = []
        self._time_wcores += time.time()-start_time
        return 1

    def process_core(self):
        """
            Changes made: instead of relaxing core, it is added to array self.wcores
        """

        # assumptions to remove
        self.garbage = set()

        # updating the cost
        self.process_selectors()
        self.cost += self.core_minweight

        if len(self.core_selectors) != 1 or len(self.core_sums) > 0:
            # process selectors in the core
            self.process_sums()
            if len(self.relaxation_vars) > 1:
                self.wcores.append(
                    (self.relaxation_vars, self.core_selectors, self.core_sums, self.core_minweight, self.core_id if self.prooflogger else None))
            else:
                # PROOF: Add unit core to base objective reformulation constraint
                if self.prooflogger:
                    self.prooflogger.write_comment("Handle unit core")
                    core_id = self.prooflogger.rup_constraint(
                        [self.relaxation_vars[0]], 1)
                    self.prooflogger.move_to_core(-1)
                    self.proof_base_reform = self.maxsat_prooflogger.base_reform_unit_core(
                        self.proof_base_reform, core_id, self.core_minweight)
                self.oracle.add_clause([self.relaxation_vars[0]])

                if self.verification_solver:
                    self.verification_solver.add_clause(
                        [self.relaxation_vars[0]])
        else:
            # unit cores are treated differently
            # (their negation is added to the hard part)
            # PROOF: Add unit core to base objective reformulation constraint
            if self.prooflogger:
                self.prooflogger.write_comment("Handle unit core")
                core_id = self.prooflogger.rup_constraint(
                    [-self.core_selectors[0]], 1)
                self.prooflogger.move_to_core(-1)
                self.proof_base_reform = self.maxsat_prooflogger.base_reform_unit_core(
                    self.proof_base_reform, core_id, self.core_minweight)

            self.oracle.add_clause([-self.core_selectors[0]])

            if self.verification_solver:
                self.verification_solver.add_clause([-self.core_selectors[0]])

        # remove unnecessary assumptions
        self.filter_assumps()

    def exhaust_ssenc_core(self, lit, cost):
        """
            when ssencoder is used, the encoder interface is different, thus exhausting looks a bit different
        """
        if self.pmres:
            return 1, lit

        bound = 1
        while 1:
            if self.oracle.solve(assumptions=[lit]):
                # PROOF: Log a possible new solution
                if self.prooflogger:
                    self.prooflogger.write_comment("Log solution if better")
                    model = self.oracle.get_model()
                    self.proof_model_improve = self.prooflogger.log_solution_with_check(
                        model)
                # PROOF: we need to argue in the proof log that we can add the other direction of the equivalence of input and output
                if self.add_partial_equivalences:
                    new_clauses = self.ssenc.lit_forced_true(
                        self.ssenc.get_output(-lit, bound-1)[0], top_id=self.topv)
                    # not really needed..?, topv won't change...
                    self.topv = self.ssenc.top_id
                    # PROOF: The clauses added to the SAT solver here are already added to the proof by logging the totalizers
                    for cl in new_clauses:
                        self.oracle.add_clause(cl)
                    if self.verification_solver:
                        for cl in new_clauses:
                            self.verification_solver.add_clause(cl)
                    if len(new_clauses):
                        for bb in range(bound):
                            flit = self.ssenc.get_output(-lit, bb)[0]
                            # PROOF: here we argue that certain outputs are set by having a SAT call with opposite assignment being UNSAT, but this should be already handled by the proof log of the SAT solver
                            if self.prooflogger:
                                self.prooflogger.write_comment(
                                    "Totalizer output is set to true")
                                self.prooflogger.rup_constraint([flit], 1)
                                # self.prooflogger.move_to_core(-1)

                            self.oracle.add_clause([flit])
                        if self.verification_solver:
                            for bb in range(bound):
                                flit = self.ssenc.get_output(-lit, bb)[0]
                                self.verification_solver.add_clause([flit])

                return bound, lit
            else:
                # PROOF: Log that the assumption is a unit core
                if self.prooflogger:
                    self.prooflogger.write_comment(
                        "Proof log core exhaustion assumption")
                    core_id = self.prooflogger.rup_constraint([-lit], 1)
                    self.proof_base_reform = self.maxsat_prooflogger.base_reform_unit_core(
                        self.proof_base_reform, core_id, cost)

                self.cost += cost
                self.totalizer_bounds[lit] = bound
                tmp, bound = self.update_sum(lit)
                lit_new = -self.ssenc.get_output(-lit, bound)[0]

                # PROOF: Log core lower bound update
                if self.prooflogger and lit_new:
                    self.prooflogger.write_comment(
                        "Update core exhaustion bound")
                    pb_def_id = self.totalizer_prooflogger.get_PbDef_invImpl_CxnId(
                        lit2var(lit_new))
                    self.maxsat_prooflogger.update_core_lower_bound(
                        lit2var(lit), lit2var(lit_new), pb_def_id, bound + 1)
                lit = lit_new

                if not lit:
                    return None, None

    def process_sum(self, lit):
        if self.pmres:
            return

        totalizer, bound = self.update_sum(lit)

        if totalizer and bound < len(totalizer.rhs):  # normal totalizer
            lnew = -totalizer.rhs[bound]
            if lnew not in self.swgt:
                self.set_bound(totalizer, bound, self.swgt[lit])
        elif self.use_ss:  # ss totalizer
            lnew = -self.ssenc.get_output(-lit, bound)[0]
            if lnew:
                if lnew not in self.swgt:
                    self.weights[lnew] = self.swgt[lit]
                    self.swgt[lnew] = self.swgt[lit]
                    self.totalizer_bounds[lnew] = bound
                    self.sums.append(lnew)

                    # PROOF: Update counter variable bound and add new definition to bound
                    # It could be that the new counter variable is actually not new in which case no lower bound update is needed. We check for this in `update_core_lower_bound`.
                    if self.prooflogger:
                        self.prooflogger.write_comment(
                            "Update counter variable lower bound if variable is new")
                        pb_def = self.totalizer_prooflogger.get_PbDef_invImpl_CxnId(
                            lit2var(lnew))
                        self.maxsat_prooflogger.update_core_lower_bound(
                            lit2var(lit), lit2var(lnew), pb_def, bound + 1)


    def update_sum(self, assump):
        """
            Add the next output variable for the totalizer.

            Changes: ss encoder
        """

        if not self.use_ss:
            return super(RC2WCE, self).update_sum(assump)
        else:
            bound = self.totalizer_bounds[assump] + 1
            new_clauses = self.ssenc.prepare_next_output(-assump, self.topv)
            self.topv = self.ssenc.top_id

            # PROOF: The clauses added to the SAT solver here are already logged by the totalizers
            for cl in new_clauses:
                self.oracle.add_clause(cl)
            if self.verification_solver:
                for cl in new_clauses:
                    self.verification_solver.add_clause(cl)

            return None, bound

    def print_stats(self):
        b = "c SOLVER-STATS"
        if self.use_ss:
            print(b, "ssenc_relax_time:", self.ssenc._time_relax)
            print(b, "ssenc_next_time:", self.ssenc._time_next)
            self.ssenc.print_stats(b+" ")

        print(b, "relax_wcores_time:", self._time_wcores)
        print(b, "satsolver_time:", self._time_satsolver)

        super(RC2WCE, self).print_stats()

        print(b, "wce_coresizes[][]:", self.stats_wce_coresizes)
        print(b, "wce_assumpssizes[]:", self.stats_wce_assumpssizes)
        print(b, "wce_cores[]:", self.stats_wce_cores)

#
# ==============================================================================


class RC2WCEStratified(RC2WCE, rc2.RC2Stratified, object):
    """
        RC2WCE augmented with BLO and stratification techniques.
    """

    def __init__(self, formula, solver='g3', adapt=False, exhaust=False, incr=False, minz=False, eq_opts=None, structure_sharing_opts=None, no_wce=False,
                 trim=0, verbose=0, add_cores=0, eqtree=False, use_upper_bounds=False,  sdivp=2.0, speed_up_assumps=0, pmres=False, verification_solver=None, prooflogger=None, maxsat_prooflogger=None, totalizer_prooflogger=None):
        """
            Constructor.
        """

        self.sdivp = sdivp

        # calling the constructor for the basic version
        super(RC2WCEStratified, self).__init__(formula, solver=solver, adapt=adapt, exhaust=exhaust, incr=incr, minz=minz, eq_opts=eq_opts,
                                               structure_sharing_opts=structure_sharing_opts, no_wce=no_wce, trim=trim, verbose=verbose, add_cores=add_cores, eqtree=eqtree,
                                               use_upper_bounds=use_upper_bounds, speed_up_assumps=speed_up_assumps, pmres=pmres, verification_solver=verification_solver, prooflogger=prooflogger, maxsat_prooflogger=maxsat_prooflogger, totalizer_prooflogger=totalizer_prooflogger)

        # NOTE: RC2WCE:s super.__init__ calls RC2Stratified:s __init__, when object is RC2WCEStratified (which inherits rc2.RC2Stratified)
        # TODO: is multiheritance only a mess?

    def init_wstr(self):
        """
            Changes: use sdivp TODO: remove?
        """

        # a mapping for stratified problem solving,
        # i.e. from a weight to a list of selectors
        self.wstr = collections.defaultdict(lambda: [])

        for s, w in six.iteritems(self.weights):
            self.wstr[w].append(s)

        # sorted list of distinct weight levels
        self.blop = sorted([w for w in self.wstr], reverse=True)

        # diversity parameter for stratification
        self.sdiv = len(self.blop) / self.sdivp

        self.done = 0

    def compute(self):
        """
            changes: use UB
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
        if self.cost == self.UB:
            self.model = self.best_model
        else:
            self.model = self.oracle.get_model()

        self.model = filter(lambda l: abs(l) in self.vmap.i2e, self.model)
        self.model = map(lambda l: int(
            copysign(self.vmap.i2e[abs(l)], l)), self.model)
        self.model = sorted(self.model, key=lambda l: abs(l))

        return self.model
