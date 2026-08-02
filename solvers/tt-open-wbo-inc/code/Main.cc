
/*!
 * \author Ruben Martins - ruben@sat.inesc-id.pt
 *
 * @section LICENSE
 *
 * MiniSat,  Copyright (c) 2003-2006, Niklas Een, Niklas Sorensson
 *           Copyright (c) 2007-2010, Niklas Sorensson
 * Open-WBO, Copyright (c) 2013-2017, Ruben Martins, Vasco Manquinho, Ines Lynce
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 *
 */

#include "utils/Options.h"
#include "utils/ParseUtils.h"
#include "utils/System.h"
#include <errno.h>
#include <signal.h>
#include <zlib.h>

#include <fstream>
#include <iostream>
#include <map>
#include <stdlib.h>
#include <string>
#include <vector>

#ifdef SIMP
#include "simp/SimpSolver.h"
#else
#include "core/Solver.h"
#endif

#include "MaxSAT.h"
#include "MaxTypes.h"
#include "ParserMaxSAT.h"
#include "ParserPB.h"
#include "Torc.h"

// Algorithms
#include "algorithms/Alg_LinearSU.h"
#include "algorithms/Alg_LinearSU_Clustering.h"
#include "algorithms/Alg_LinearSU_Mod.h"
#include "algorithms/Alg_MSU3.h"
#include "algorithms/Alg_OLL.h"
#include "algorithms/Alg_OLL_Mod.h"
#include "algorithms/Alg_PartMSU3.h"
#include "algorithms/Alg_WBO.h"
#include "algorithms/Alg_OBV.h"
#include "algorithms/Alg_BLS.h"

#define VER1_(x) #x
#define VER_(x) VER1_(x)
#define SATVER VER_(SOLVERNAME)
#define VER VER_(VERSION)

using NSPACE::BoolOption;
using NSPACE::DoubleOption;
using NSPACE::IntOption;
using NSPACE::IntRange;
using NSPACE::DoubleRange;
using NSPACE::OutOfMemoryException;
using NSPACE::StringOption;
using NSPACE::cpuTime;
using NSPACE::parseOptions;
using namespace openwbo;

//=================================================================================================

static MaxSAT *mxsolver;

static void SIGINT_exit(int signum) {
  mxsolver->printAnswer(_UNKNOWN_);
  exit(_UNKNOWN_);
}

#include "Test.h"

// void test_encoding();

//=================================================================================================
// Main:

int main(int argc, char **argv) {
  printf(
      "c\nc TT-Open-WBO-Inc:\t an Anytime MaxSAT Solver -- based on %s\n",
      SATVER);
  printf("c Version:\t Development after MaxSAT Evaluation 2024\n");
  printf("c Author:\t Alexander Nadel\n");
  printf("c Authors of the baseline SAT-based solver Open-WBO-Inc:\t Saurabh Joshi, Prateek Kumar, Ruben Martins, Sukrut Rao\n");
  printf("c Authors of the local search solver NuWLS-c-2023:\t Yi Chu, Shaowei Cai, Chuan Luo\n");
  printf("c Contact:\t alexandernad@technion.ac.il -- "
         "http://www.cs.tau.ac.il/research/alexander.nadel/\nc\n");
  try {
    NSPACE::setUsageHelp("c USAGE: %s [options] <input-file>\n\n");

#if defined(__linux__)
    fpu_control_t oldcw, newcw;
    _FPU_GETCW(oldcw);
    newcw = (oldcw & ~_FPU_EXTENDED) | _FPU_DOUBLE;
    _FPU_SETCW(newcw);
    printf(
        "c WARNING: for repeatability, setting FPU to use double precision\n");
#endif

    BoolOption printmodel("Open-WBO", "print-model", "Print model.\n", true);
    
    IntOption disable_buffering("TTOpenWboInc", "disable-buffering", "Disable buffering to stdout.\n", 0, IntRange(0, 1));  
	
    IntOption num_tests("Test", "num_tests", "Number of tests\n", 0,
                        IntRange(0, 10000000));

    IntOption test_rhs("Test", "test_rhs",
                       "RHS for a custom encoding test\n", 0,
                       IntRange(0, 10000000));

    IntOption test_rhs2("Test", "test_rhs2",
                        "RHS for a custom encoding test for the second tree\n", 0,
                        IntRange(0, 10000000));

    IntOption test_nsoft("Test", "test_nsoft",
                         "Nsoft for a custom encoding test\n", 0,
                         IntRange(0, 10000000));

    IntOption test_join("Test", "test_join",
                        "Join for a custom encoding test\n", 0, IntRange(0, 1));

    IntOption verbosity("Open-WBO", "verbosity",
                        "Verbosity level (0=minimal, 1=more).\n", 0,
                        IntRange(0, 1));

    IntOption algorithm("Open-WBO", "algorithm",
                        "Search algorithm "
                        "(0=wbo,1=linear-su,2=msu3,3=part-msu3,4=oll,5=best,6="
                        "bmo,7=obv,8=mcs)\n",
                        5, IntRange(0, 8));

    IntOption partition_strategy("PartMSU3", "partition-strategy",
                                 "Partition strategy (0=sequential, "
                                 "1=sequential-sorted, 2=binary)"
                                 "(only for unsat-based partition algorithms).",
                                 2, IntRange(0, 2));

    IntOption graph_type("PartMSU3", "graph-type",
                         "Graph type (0=vig, 1=cvig, 2=res) (only for unsat-"
                         "based partition algorithms).",
                         2, IntRange(0, 2));

    BoolOption bmo("Open-WBO", "bmo", "BMO search.\n", true);

    IntOption cardinality("Encodings", "cardinality",
                          "Cardinality encoding (0=cardinality networks, "
                          "1=totalizer, 2=modulo totalizer).\n",
                          1, IntRange(0, 2));

    IntOption amo("Encodings", "amo", "AMO encoding (0=Ladder).\n", 0,
                  IntRange(0, 0));

    IntOption pb("Encodings", "pb", "PB encoding (0=SWC,1=GTE,2=GTECluster).\n",
                 1, IntRange(0, 2));

    IntOption formula("Open-WBO", "formula",
                      "Type of formula (0=WCNF, 1=OPB).\n", 0, IntRange(0, 1));

    IntOption weight(
        "WBO", "weight-strategy",
        "Weight strategy (0=none, 1=weight-based, 2=diversity-based).\n", 2,
        IntRange(0, 2));

    BoolOption symmetry("WBO", "symmetry", "Symmetry breaking.\n", true);

    IntOption symmetry_lim(
        "WBO", "symmetry-limit",
        "Limit on the number of symmetry breaking clauses.\n", 500000,
        IntRange(0, INT32_MAX));

    IntOption cluster_algorithm("Clustering", "ca",
                                "Clustering algorithm "
                                "(0=none, 1=DivisiveMaxSeparate)",
                                1, IntRange(0, 1));
    IntOption num_clusters("Clustering", "c", "Number of agglomerated clusters",
                           100000, IntRange(1, INT_MAX));

    IntOption rounding_strategy(
        "Clustering", "rs",
        "Statistic used to select"
        " common weights in a cluster (0=Mean, 1=Median, 2=Min)",
        0, IntRange(0, 2));

    IntOption num_conflicts(
      "Incomplete","conflicts","Limit on the number of conflicts.\n", 1000,
      IntRange(0, INT32_MAX));

    IntOption num_iterations(
      "Incomplete","iterations","Limit on the number of iterations.\n", INT32_MAX,
      IntRange(0, INT32_MAX));

	// Changed to the more convinient IntOption
    IntOption local("Incomplete", "local", "Local limit on the number of conflicts.\n", 1);

	IntOption polConservative("TTOpenWboInc", "conservative", "Apply conservative polarity heuristic?\n", 1);
	BoolOption conservativeUseAllVars("TTOpenWboInc", "conservative_use_all_vars", "Re-use the polarity of all the variables within the conservative approach (or, otherwise, only the initial once)?\n", true);	
	IntOption polOptimistic("TTOpenWboInc", "optimistic", "Set target variables' polarity to the optimum?\n", 1);	
	//W: -target_vars_bump_val=750 -target_vars_bump_rel_weights=1 -target_vars_bump_max_rand_val=1000
	//U: -target_vars_bump_val=50 -target_vars_bump_rel_weights=0 -target_vars_bump_max_rand_val=0
#ifndef USE_TOPOR
	IntOption targetVarsBumpVal("TTOpenWboInc", "target_vars_bump_val", "Bump factor of the activity of the targets at the beginning\n", 113);	
#else
	IntOption targetVarsBumpVal("TTOpenWboInc", "target_vars_bump_val", "Bump factor of the activity of the targets at the beginning\n", 750);	
#endif
	// Bool
	IntOption targetVarsBumpRelWeights("TTOpenWboInc", "target_vars_bump_rel_weights", "Bump the variable scores, where the bump value is relative to the weights?\n", 1);	
#ifndef USE_TOPOR
	IntOption targetVarsBumpMaxRandVal("TTOpenWboInc", "target_vars_bump_max_rand_val", "Maximal random bump factor\n", 552);	
#else
	IntOption targetVarsBumpMaxRandVal("TTOpenWboInc", "target_vars_bump_max_rand_val", "Maximal random bump factor\n", 1000);	
#endif
	IntOption msMaxEpochs("TTOpenWboInc", "ms_max_epochs", "Mutation sampling: the maximal number of epochs, even if there is an improvement. If there is no improvement or the maximal number of epochs is over, fall back to BMO\n", 10000000);	
	IntOption msMutationClasses("TTOpenWboInc", "ms_mutation_classes", "Mutation sampling: the number of mutation classes\n", 1);
	IntOption msConflictsPerSatCall("TTOpenWboInc", "ms_conflicts_per_sat_call", "Mutation sampling: the maximal number of conflicts per SAT call when testing a mutation\n", 1000);
	IntOption msSatCallsPerEpoch("TTOpenWboInc", "ms_sat_calls_per_iteration", "Mutation sampling: the maximal number of SAT calls per epoch\n", 150);
	BoolOption msDisableTorc("TTOpenWboInc", "ms_disable_torc", "Mutation sampling: disable TORC when looking for mutations\n", false);
    BoolOption msStayNearStartingModel("TTOpenWboInc", "ms_stay_near_starting_model", "Mutation sampling: stay near the starting model (rather the best model) when learning the mutations\n", false);
    IntOption msConflictsLookNearMutation("TTOpenWboInc", "ms_conflicts_look_near_mutation", "Mutation sampling: the maximal number of conflicts per SAT call when looking near a mutation\n", 1000);
    IntOption msSortLitsStrat("TTOpenWboInc", "ms_sort_lits_strategy", "Mutation sampling: 0: don't sort mutation literals; 1: shuffle mutation literals randomly, 2: sort mutation literals -- frequent first, 3: sort mutation literals -- frequent last \n", 1, IntRange(0, 3));
    BoolOption msSiftRemaining("TTOpenWboInc", "ms_sift_remaining", "Mutation sampling: sift the remaining mutation-candidate literals?\n", true);
    BoolOption msSiftRemainingOnlyWhenOptimized("TTOpenWboInc", "ms_sift_remaining_only_when_optimized", "Mutation sampling: sift the remaining mutation-candidate literals only when an optimizing model found?\n", false);
    BoolOption msAfterRepair("TTOpenWboInc", "ms_after_repair", "Mutation sampling: apply after repair?\n", true);
    DoubleOption msModelPerSecThr("TTOpenWboInc", "ms_model_per_sec_thr", "Stop mutation-optimization forever when the improving models-per-second threshold is too low. If non-0, ms_sat_calls_per_iteration is not taken into account for any iteration where ms_model_per_sec_thr is considered", 0, DoubleRange(0, true, HUGE_VAL, true));
    DoubleOption msPropPerModelThr("TTOpenWboInc", "ms_prop_per_model_thr", "Stop mutation-optimization forever when the improving propagation-per-model threshold is too high. If non-0, ms_sat_calls_per_iteration is not taken into account for any iteration where ms_model_per_sec_conf is considered", 1000000, DoubleRange(0, true, HUGE_VAL, true));
    IntOption msModelPerSecOnlyForFirstInv("TTOpenWboInc", "ms_model_per_sec_only_for_first_inv", "Mutation sampling: apply model-per-second threshold only for the first mutation-optimization invocation?\n", 0, IntRange(0, 1));
    IntOption msMutCombUseBestModel("TTOpenWboInc", "ms_mut_comb_best_model", "Mutation sampling: apply mutation combination to the best model so far (or, otherwise, the best model)?\n", 0, IntRange(0, 1));
    IntOption msInitBadStrat("TTOpenWboInc", "ms_init_bad_strat", "Mutation sampling: how to initialize the bad observables at the beginning of each epoch: 0 : re-use remaining bad's from the previous epoch; 1: initialize with observables which hold in the best model so far; 2: initialize with observables which hold in the initial model\n", 2, IntRange(0, 2));
    DoubleOption msRndFreqForMublox("TTOpenWboInc", "ms_rnd_freq", "Mutation sampling: the frequency with which the decision heuristic tries to choose a random variable during MuBlox execution (corresponds to the rnd-freq parameter in Glucose", 0, DoubleRange(0, true, 1, true));
    IntOption msMinLBDFrozenClauseForMublox("TTOpenWboInc", "ms_min_lbd_frozen_clause", "Mutation sampling: the value of Glucose's parameter minLBDFrozenClause for the MuBlox phazes of the algorithm\n", 30);
    IntOption msConflToChrono("TTOpenWboInc", "ms_confl_to_chrono", "OBV-BS/Clustering: the value of Glucose's parameter confl-to-chrono\n", 0);
    IntOption msChrono("TTOpenWboInc", "ms_chrono", "OBV-BS/Clustering: the value of Glucose's parameter chrono\n", -1);
    IntOption poContLocalImpr("TTOpenWboInc", "po_cont_local_impr", "Polosat: continue Polosat's first epoch as long as there is a local improvement w.r.t the first model, even if it's not an improvement w.r.t globally best model. Relevant only if the adaptive strategy is on\n", 0);
    IntOption mrsBeaverSizeSwitchToComplete("TTOpenWboInc", "mrs_beaver_size_switch_to_complete", "Mrs. Beaver: the maximal size of the encoding to switch to complete part\n", 1000000);
    IntOption mrsBeaverEachIterStartBestModel("TTOpenWboInc", "mrs_beaver_each_iter_start_best_model", "Mrs. Beaver: make sure each iterations starts with the best (rather than the original) model\n", 0);
    IntOption blockBestModel("TTOpenWboInc", "block_best_model", "Block each best model\n", 0);
    IntOption polosatTurnOffHighLevelConfThrForIters("TTOpenWboInc", "ps_turn_off_high_lvl_confthr_for_iters", "Polosat: turn off higher-level coflict-threshold for iterations?\n", 0);    
    DoubleOption optimisticMaxSoftFraction("TTOpenWboInc", "optimistic_max_soft_percent", "The maximal fraction of soft clauses to leave the optimistic polarity selection enabled (if optimistic is on)\n", 1., DoubleRange(0., true, 1., true));
    DoubleOption conservativeMaxSoftFraction("TTOpenWboInc", "conservative_max_soft_percent", "The maximal fraction of soft clauses to leave the conservative polarity selection enabled (if conservative is on)\n", 1., DoubleRange(0., true, 1., true));
    IntOption partialSumFailItersToSwitch("TTOpenWboInc", "partial_sum_fail_iters_to_switch", "Partial sum: the window size of failing Mrs. Beaver iterations to use layers of partial sum too (0 for not applying partial sum)\n", 0);
    IntOption partialSumLayersThr("TTOpenWboInc", "partial_sum_layers_thr", "Partial sum: the threshold on the number of layers in a partial sum (0: no threshold)\n", 0);
    IntOption partialSumConflicts("TTOpenWboInc", "partial_sum_conflicts", "Partial sum: #conficts in Mrs. Beaver invocations\n", 1000);
    IntOption weightedObvBsFirstIterStrat("TTOpenWboInc", "weighted_obvbs_firstiter_strat", "weighted: 0: don't use OBV-BS; 1: use OBV-BS immediately after the first SAT invocation (replace MS, if MS is on)\n", 0, IntRange(0, 1));
    IntOption wobsAdaptiveStoppedStopMs("TTOpenWboInc", "wobs_adaptive_stopped_stop_ms", "Weighted OBV-BS: 0: if adaptive policy stopped OBV-BS execution, don't stop MS; 1: if adaptive policy stopped OBV-BS execution, stop MS\n", 0, IntRange(0, 1));
    DoubleOption wobsAdaptiveNotStoppedMSThrMult("TTOpenWboInc", "wobs_adaptive_not_stopped_ms_thr_mult", "Weighted OBV-BS: if adaptive policy didn't stop OBV-BS execution, multiply MS's adaptive threshold by this value\n", 1.);
    IntOption msObvStrat("TTOpenWboInc", "ms_obv_strat", "MS and Polosat OBV-BS integration strategy: 0: don't use OBV-BS in MS; 1: fully switch to OBV-BS-like alg. in MS;\
       2: switch to OBV-BS in MS, but try standard MS call too, if OBV-BS failed to generate a model; 3: switch to OBV-BS in MS, but try standard MS call too, if OBV-BS failed to generate a *better* model;\
       4: switch to Full-Prefix in MS, but try standard MS call too, if Full-Prefix failed to generate a model; 5: switch to Full-Prefix in MS, but try standard MS call too, if Full-Prefix failed to generate a *better* model;\
       6: use standard MS, but try OBV-BS too, if standard MS failed to generate a model; 7: use standard MS, but try OBV-BS too, if standard MS failed to generate a *better* model;\
       8: use standard MS, but try Full-Prefix too, if standard MS failed to generate a model; 9: use standard MS, but try Full-Prefix too, if standard MS failed to generate a *better* model\
       10: fully switch to Full-Prefix in MS;\n", 2, IntRange(0, 10));
    IntOption mrsBeaverPolosatRegulateStrat("TTOpenWboInc", "mrs_beaver_polosat_regulate_strat", "Mrs. Beaver: 0: no change to default; 1 (relevant only if ms_obv_strat>0): switch off ms_obv_strat after the initial SAT invocation in Mrs. Beaver; 2 (relevant only if ms_obv_strat>0): switch off ms_obv_strat before the complete part; 3: switch off polosat before the complete part (if not already off)\n", 3, IntRange(0, 3));
    IntOption mrsBeaverApplySizeThrDuringInitialPolosat("TTOpenWboInc", "mrs_beaver_apply_size_thr_during_initial_polosat", "Mrs. Beaver: apply the size threshold *during* the initial polosat\n", 1);
    IntOption printEveryModel("TTOpenWboInc", "print_every_model", "Print every new improving model explicitly\n", 0);
    IntOption nuwlsMode("TTOpenWboInc", "nuwls_mode", "NuWLS mode of usage (0: no NuWLS; 1: Run NuWLS once\n", 1);
    IntOption nuwlsIsExternalTimeLimit("TTOpenWboInc", "nuwls_is_external_time_limit", "NuWLS read the time-limit from the external parameter \n", 0);
    IntOption nuwlsExternalTimeLimit("TTOpenWboInc", "nuwls_external_time_limit", "NuWLS the external time-limit (relevant if nuwls_is_external_time_limit is 1) \n", 20);
    IntOption satlikeMode("TTOpenWboInc", "satlike_mode", "SatLike mode of usage (0: no SatLike; 1: Run SatLike once; 2: Run SatLike more than once; start counting time till next iteration from the end of the last SatLike invocation; 3: Similar to 2, but update the time counting until next iteration, whenever a new best model is found\n", 0);
    IntOption satlikeInvsThr("TTOpenWboInc", "satlike_invs_thr", "SatLike: threshold on the number of invocations (0: no threshold; n>0: at most n invocations)\n", 2);
    IntOption satlikeTimeThr("TTOpenWboInc", "satlike_time_thr", "Time threshold in seconds for SatLike solving\n", 15);
    IntOption satlikeInitTimeThr("TTOpenWboInc", "satlike_init_time_thr", "Time threshold in seconds for SatLike initialization, that is, inside building the neighbourhood relations (0 means no threshold)\n", 5);
    IntOption satlikePreInitTimeThr("TTOpenWboInc", "satlike_pre_init_time_thr", "Time threshold in seconds for SatLike pre-initialization, that is, *before* building the neighbourhood relations (0 means no threshold)\n", 1);
    IntOption satlikePreInitMaxClss("TTOpenWboInc", "satlike_pre_init_max_clss", "Maximal number of clauses in SatLike pre-initialization to skip building the neighbourhood relations\n", 10000000);
    IntOption lsMaxFlips("TTOpenWboInc", "ls_max_flips", "SatLike/NuWLS initialization: the maximal number of flips\n", 10000000);
    IntOption lsMaxNonImproveFlip("TTOpenWboInc", "ls_max_non_improve_flip", "SatLike/NuWLS initialization: the maximal number of non-improving flips\n", 10000000);
    IntOption satlikeMaxFlipsReduceBeyondClsNum("TTOpenWboInc", "satlike_max_flips_reduce_beyond_cls_num", "SatLike: is non-0 and clss_num > satlike_max_flips_reduce_beyond_cls_num, divide satlike_max_flips and satlike_max_non_improve_flip by (clss_num / satlike_max_flips_reduce_beyond_cls_num)\n", 0);
    IntOption satlikeReinvokeTimeThr("TTOpenWboInc", "satlike_reinvoke_time_thr", "Time threshold in seconds before SatLike reinvocation (don't forget to also set satlike_mode to 2 or 3)\n", 60);
    DoubleOption satlikeReinvokeMult("TTOpenWboInc", "satlike_reinvoke_mult", "The double value by which SatLike threshold is multiplied upon each reinvocation\n", 1.);
    IntOption satlikeMimicMse21("TTOpenWboInc", "satlike_mimic_mse21", "SatLike: mimic MSE'21?\n", 0);    
    IntOption totProp0s("TTOpenWboInc", "tot_prop_0s", "Propagate 0's in the totalizer encoding?\n", 0, IntRange(0, 1));
    IntOption totBuildLayered("TTOpenWboInc", "tot_build_layered", "Totalizer encoding: build layer-by-layer\n", 0, IntRange(0, 1));
    IntOption msSatInvToReinvoke("TTOpenWboInc", "ms_sat_inv_to_reinvoke", "Polosat: reinvoke after ms_sat_inv_to_reinvoke unsuccesfull SAT invocations (0: never reinvoke)\n", 0);
    DoubleOption msSatInvToReinvokeMult("TTOpenWboInc", "ms_sat_inv_to_reinvoke_mult", "Polosat: the multiplication factor for ms_sat_inv_to_reinvoke when reinvoking\n", 1.);
    DoubleOption msReinvokeMultThr("TTOpenWboInc", "ms_reinvoke_mult_thr", "Polosat: multiply the threshold ms_model_per_sec_thr by ms_reinvoke_mult_thr when reinvoing Polosat\n", 1.);
    DoubleOption msReinvokeMultThrMin("TTOpenWboInc", "ms_reinvoke_mult_thr_min", "Polosat: the minimal possible threshold (relevant when ms_reinvoke_mult_thr<1)\n", 0.001);    
    
    IntOption msVerbosity("TTOpenWboInc", "ms_verbosity", "Mutation sampling: verbosity (0: not verbose at all; only print when interrupted or finished; 1: print o and timeo messages; 2: print some info about the alg. progress; 3: debugging)\n", 2, IntRange(0, 3));
    
    parseOptions(argc, argv, true);
    
      
    if (disable_buffering)
	{
		printf("c -disable-buffering=1 ==> buffering disabled\n");
		setvbuf(stdout, NULL, _IONBF, 0);
	}  

    if ((int)num_tests) {
      if ((int)test_join) {
        for (int i = 0; i < (int)num_tests; i++) {
          test_encoding_join();
        }
      } else {
        for (int i = 0; i < (int)num_tests; i++) {
          test_encoding();
        }
      }

      return 0;
    }

	Torc::Instance()->SetPolConservative((bool)polConservative);
	Torc::Instance()->SetConservativeAllVars(conservativeUseAllVars);
	Torc::Instance()->SetPolOptimistic((bool)polOptimistic);
	Torc::Instance()->SetTargetVarsBumpVal(targetVarsBumpVal);	
	Torc::Instance()->SetBumpRelWeights((bool)targetVarsBumpRelWeights);	
	Torc::Instance()->SetTargetBumpMaxRandVal(targetVarsBumpMaxRandVal);	
	Torc::Instance()->SetMsMutationClasses(msMutationClasses);
	Torc::Instance()->SetMsConflictsPerSatCall(msConflictsPerSatCall);
	Torc::Instance()->SetMsSatCallsPerEpoch(msSatCallsPerEpoch);
	Torc::Instance()->SetMsMaxEpochs(msMaxEpochs);
	Torc::Instance()->SetMsDisableTorc(msDisableTorc);
	Torc::Instance()->SetMsStayNearStartingModel(msStayNearStartingModel);
	Torc::Instance()->SetMsConflictsLookNearMutation(msConflictsLookNearMutation);
	Torc::Instance()->SetMsSortLitsStrat(msSortLitsStrat);
	Torc::Instance()->SetMsSiftRemaining(msSiftRemaining);
	Torc::Instance()->SetMsSiftRemainingOnlyWhenOptimized(msSiftRemainingOnlyWhenOptimized);
	Torc::Instance()->SetMsAfterRepair(msAfterRepair);
	Torc::Instance()->SetMsModelPerSecThr(msModelPerSecThr);
	Torc::Instance()->SetMsPropPerModelThr(msPropPerModelThr);
	Torc::Instance()->SetMsModelPerSecOnlyForFirstInv((bool)msModelPerSecOnlyForFirstInv);
	Torc::Instance()->SetMsMutCombUseBestModel((bool)msMutCombUseBestModel);
	Torc::Instance()->SetMsInitBadStrat(msInitBadStrat);
	Torc::Instance()->SetMsRndFreqForMublox(msRndFreqForMublox);
	Torc::Instance()->SetMsMinLBDFrozenClauseForMublox(msMinLBDFrozenClauseForMublox);
	Torc::Instance()->SetConflToChrono(msConflToChrono);
    Torc::Instance()->SetChrono(msChrono);
    Torc::Instance()->SetPoContLocalImpr(poContLocalImpr);
    Torc::Instance()->SetMrsBeaverSizeSwitchToComplete(mrsBeaverSizeSwitchToComplete);
    Torc::Instance()->SetMrsBeaverEachIterStartBestModel(mrsBeaverEachIterStartBestModel);    
    Torc::Instance()->SetBlockBestModel(blockBestModel);    
	Torc::Instance()->SetPolosatTurnOffHighLevelConfThrForIters(polosatTurnOffHighLevelConfThrForIters);
	Torc::Instance()->SetPartialSumFailItersToSwitch(partialSumFailItersToSwitch);
	Torc::Instance()->SetPartialSumLayersThr(partialSumLayersThr);
	Torc::Instance()->SetPartialSumConflicts(partialSumConflicts);
	Torc::Instance()->SetWeightedObvBsFirstIterStrat(weightedObvBsFirstIterStrat);
	Torc::Instance()->SetWobsAdaptiveStoppedStopMs(wobsAdaptiveStoppedStopMs);
    Torc::Instance()->SetWobsAdaptiveNotStoppedMSThrMult(wobsAdaptiveNotStoppedMSThrMult);
    Torc::Instance()->SetMsObvStrat(msObvStrat);
    Torc::Instance()->SetMrsBeaverPolosatRegulateStrat(mrsBeaverPolosatRegulateStrat);
    Torc::Instance()->SetMrsBeaverApplySizeThrDuringInitialPolosat(mrsBeaverApplySizeThrDuringInitialPolosat);
    Torc::Instance()->SetPrintEveryModel(printEveryModel);
    Torc::Instance()->SetNuwlsMode(nuwlsMode);
    Torc::Instance()->SetNuwlsIsExternalTimeLimit(nuwlsIsExternalTimeLimit);   
    Torc::Instance()->SetNuwlsExternalTimeLimit(nuwlsExternalTimeLimit);   
    Torc::Instance()->SetSatlikeMode(satlikeMode);
    Torc::Instance()->SetSatlikeInvsThr(satlikeInvsThr);
    Torc::Instance()->SetSatlikeTimeThr(satlikeTimeThr);
    Torc::Instance()->SetSatlikeInitTimeThr(satlikeInitTimeThr);
    Torc::Instance()->SetSatlikePreInitTimeThr(satlikePreInitTimeThr);
    Torc::Instance()->SetSatlikePreInitMaxClss(satlikePreInitMaxClss);
    Torc::Instance()->SetSatlikeMaxFlips(lsMaxFlips);
    Torc::Instance()->SetSatlikeMaxNonImproveFlip(lsMaxNonImproveFlip);
    Torc::Instance()->SetSatlikeMaxFlipsReduceBeyondClsNum(satlikeMaxFlipsReduceBeyondClsNum);
    Torc::Instance()->SetSatlikeReinvokeTimeThr(satlikeReinvokeTimeThr);
    Torc::Instance()->SetSatlikeReinvokeMult(satlikeReinvokeMult);
    Torc::Instance()->SetSatlikeMimicMse21(satlikeMimicMse21);
    Torc::Instance()->SetTotProp0s(totProp0s);
    Torc::Instance()->SetTotBuildLayered(totBuildLayered);
    Torc::Instance()->SetMsSatInvToReinvoke(msSatInvToReinvoke);
    Torc::Instance()->SetMsSatInvToReinvokeMult(msSatInvToReinvokeMult);
    Torc::Instance()->SetMsReinvokeMultThr(msReinvokeMultThr);
    Torc::Instance()->SetMsReinvokeMultThrMin(msReinvokeMultThrMin);
    Torc::Instance()->SetMsVerbosity(msVerbosity);
    double initial_time = cpuTime();
    MaxSAT *S = NULL;

    Statistics rounding_statistic =
        static_cast<Statistics>((int)rounding_strategy);

    switch ((int)algorithm) {
    case _ALGORITHM_WBO_:
      S = new WBO(verbosity, weight, symmetry, symmetry_lim);
      break;

    case _ALGORITHM_LINEAR_SU_:
      if ((int)(cluster_algorithm) == 1) {
        S = new LinearSUMod(verbosity, bmo, cardinality, pb,
                            ClusterAlg::_DIVISIVE_, rounding_statistic,
                            (int)(num_clusters));
      } else {
        S = new LinearSU(verbosity, bmo, cardinality, pb);
      }
      break;

    case _ALGORITHM_PART_MSU3_:
      S = new PartMSU3(verbosity, partition_strategy, graph_type, cardinality);
      break;

    case _ALGORITHM_MSU3_:
      S = new MSU3(verbosity);
      break;

    case _ALGORITHM_LSU_CLUSTER_:
      S = new LinearSUClustering(verbosity, bmo, cardinality, pb,
                                 ClusterAlg::_DIVISIVE_, rounding_statistic,
                                 (int)(num_clusters));
      break;

    case _ALGORITHM_LSU_MRSBEAVER_:
      S = new OBV(verbosity, cardinality, num_conflicts, num_iterations, (bool)local); 
      break;

    case _ALGORITHM_LSU_MCS_:
      // The default num_iterations changed from 100000, so the default MCS call has changed
      S = new BLS(verbosity, cardinality, num_conflicts, num_iterations, (bool)local);
      break;

    case _ALGORITHM_OLL_:
      if ((int)(cluster_algorithm) == 1) {
        S = new OLLMod(verbosity, cardinality, ClusterAlg::_DIVISIVE_,
                       rounding_statistic, (int)(num_clusters));
      } else {
        S = new OLL(verbosity, cardinality);
      }
      break;

    case _ALGORITHM_BEST_:
      break;

    default:
      printf("c Error: Invalid MaxSAT algorithm.\n");
      printf("s UNKNOWN\n");
      exit(_ERROR_);
    }

    signal(SIGXCPU, SIGINT_exit);
    signal(SIGTERM, SIGINT_exit);

    if (argc == 1) {
      printf("c Error: no filename.\n");
      printf("s UNKNOWN\n");
      exit(_ERROR_);
    }

    gzFile in = (argc == 1) ? gzdopen(0, "rb") : gzopen(argv[1], "rb");
    if (in == NULL)
      printf("c ERROR! Could not open file: %s\n",
             argc == 1 ? "<stdin>" : argv[1]),
          printf("s UNKNOWN\n"), exit(_ERROR_);

    MaxSATFormula *maxsat_formula = new MaxSATFormula();

    if ((int)formula == _FORMAT_MAXSAT_) {
      parseMaxSATFormula(in, maxsat_formula);
      maxsat_formula->setFormat(_FORMAT_MAXSAT_);
    } else {
      ParserPB *parser_pb = new ParserPB();
      parser_pb->parsePBFormula(argv[1], maxsat_formula);
      maxsat_formula->setFormat(_FORMAT_PB_);
    }
    gzclose(in);

    if ((int)test_rhs) {
      if ((int)test_rhs2) {
        test_encoding(maxsat_formula, (uint64_t)test_rhs, (uint64_t)test_rhs2,
                      (uint64_t)test_nsoft);
      } else {
        test_encoding(maxsat_formula, (uint64_t)test_rhs);
      }
      return 0;
    }

    printf("c |                                                                "
           "                                       |\n");
    printf("c ========================================[ Problem Statistics "
           "]===========================================\n");
    printf("c |                                                                "
           "                                       |\n");

    if (maxsat_formula->getFormat() == _FORMAT_MAXSAT_)
      printf(
          "c |  Problem Format:  %17s                                         "
          "                          |\n",
          "MaxSAT");
    else
      printf(
          "c |  Problem Format:  %17s                                         "
          "                          |\n",
          "PB");

    if (maxsat_formula->getProblemType() == _UNWEIGHTED_)
      printf("c |  Problem Type:  %19s                                         "
             "                          |\n",
             "Unweighted");
    else
      printf("c |  Problem Type:  %19s                                         "
             "                          |\n",
             "Weighted");

    printf("c |  Number of variables:  %12d                                    "
           "                               |\n",
           maxsat_formula->nVars());
    printf("c |  Number of hard clauses:    %7d                                "
           "                                   |\n",
           maxsat_formula->nHard());
    printf("c |  Number of soft clauses:    %7d                                "
           "                                   |\n",
           maxsat_formula->nSoft());
    printf("c |  Number of cardinality:     %7d                                "
           "                                   |\n",
           maxsat_formula->nCard());
    printf("c |  Number of PB :             %7d                                "
           "                                   |\n",
           maxsat_formula->nPB());
    double parsed_time = cpuTime();

    printf("c |  Parse time:           %12.2f s                                "
           "                                 |\n",
           parsed_time - initial_time);
    printf("c |                                                                "
           "                                       |\n");
	
	const auto clss = maxsat_formula->nSoft() + maxsat_formula->nHard();
	const double softsFract = (double)maxsat_formula->nSoft()/(double)clss;
	
	if (polOptimistic && clss != 0 && optimisticMaxSoftFraction < 1. && softsFract > optimisticMaxSoftFraction) 
	{
		Torc::Instance()->SetPolOptimistic((bool)(polOptimistic = 0));
		printf("c | optimistic polarity turned off, since the softs comprise %f of the clauses > %f |\n", softsFract, (double)optimisticMaxSoftFraction);	
	}
	
	if (polConservative && clss != 0 && conservativeMaxSoftFraction < 1. && softsFract > conservativeMaxSoftFraction) 
	{
		Torc::Instance()->SetPolConservative((bool)(polConservative = 0));
		printf("c | conservative polarity turned off, since the softs comprise %f of the clauses > %f |\n", softsFract, (double)conservativeMaxSoftFraction);	
	}
	
    if (algorithm == _ALGORITHM_BEST_) {
	  assert(S == NULL);
	  
      if (maxsat_formula->getProblemType() == _UNWEIGHTED_) {
#ifndef USE_TOPOR
        if (!targetVarsBumpVal.is_set_by_user())
        {
			Torc::Instance()->SetTargetVarsBumpVal(0);
			printf("c | best-alg-selector overriden target_vars_bump_val to 0, since it hadn't been set by the user |\n");	
		}
#else
		if (!targetVarsBumpVal.is_set_by_user())
        {
			Torc::Instance()->SetTargetVarsBumpVal(50);
			printf("c | best-alg-selector overriden target_vars_bump_val to 1, since it hadn't been set by the user |\n");	
		}
		//IntOption targetVarsBumpRelWeights("TTOpenWboInc", "target_vars_bump_rel_weights", "Bump the variable scores, where the bump value is relative to the weights?\n", 1);	
		if (!targetVarsBumpRelWeights.is_set_by_user())
        {
			Torc::Instance()->SetBumpRelWeights(0);
			printf("c | best-alg-selector overriden target_vars_bump_rel_weights to 0, since it hadn't been set by the user |\n");	
		}
		
	    //IntOption targetVarsBumpMaxRandVal("TTOpenWboInc", "target_vars_bump_max_rand_val", "Maximal random bump factor\n", 552);	
	    if (!targetVarsBumpMaxRandVal.is_set_by_user())
        {			
			Torc::Instance()->SetTargetBumpMaxRandVal(0);
			printf("c | best-alg-selector overriden target_vars_bump_max_rand_val to 0, since it hadn't been set by the user |\n");	
		}
#endif
		//DoubleOption msModelPerSecThr("TTOpenWboInc", "ms_model_per_sec_thr", "Stop mutation-optimization forever when the improving models-per-second threshold is too low. If non-0, ms_sat_calls_per_iteration is not taken into account for any iteration where ms_model_per_sec_thr is considered", 0, DoubleRange(0, true, HUGE_VAL, true));
		if (!msModelPerSecThr.is_set_by_user())
        {
#ifndef USE_TOPOR			
			Torc::Instance()->SetMsModelPerSecThr(2.5);
			printf("c | best-alg-selector overriden ms_model_per_sec_thr to 2.5, since it hadn't been set by the user |\n");	
#endif
		}
		//DoubleOption msPropPerModelThr("TTOpenWboInc", "ms_prop_per_model_thr", "Stop mutation-optimization forever when the improving propagation-per-model threshold is too high. If non-0, ms_sat_calls_per_iteration is not taken into account for any iteration where ms_model_per_sec_conf is considered", 1000000, DoubleRange(0, true, HUGE_VAL, true));
		if (!msPropPerModelThr.is_set_by_user())
        {
#ifndef USE_TOPOR			
			Torc::Instance()->SetMsPropPerModelThr(0);
			printf("c | best-alg-selector overriden ms_prop_per_model_thr to 0, since it hadn't been set by the user |\n");	
#endif
		}
		
		if (!msMutationClasses.is_set_by_user())
		{
			Torc::Instance()->SetMsMutationClasses(0);
			printf("c | best-alg-selector overriden ms_mutation_classes to 0, since it hadn't been set by the user |\n");	
		}
		
		if (!msChrono.is_set_by_user())
		{
			Torc::Instance()->SetChrono(100);
			printf("c | best-alg-selector overriden ms_chrono to 100, since it hadn't been set by the user |\n");	
		}
		
		if (!msObvStrat.is_set_by_user())
		{
			Torc::Instance()->SetMsObvStrat(7);
			printf("c | best-alg-selector overriden ms_obv_strat to 7, since we're in unweighted mode and it hadn't been set by the user |\n");	
		}
		
		if (!satlikeInitTimeThr.is_set_by_user())
		{
			Torc::Instance()->SetSatlikeInitTimeThr(30);
			printf("c | best-alg-selector overriden satlikeInitTimeThr to 30, since it hadn't been set by the user |\n");	
		}
				
		if (!cardinality.is_set_by_user())
		{
			cardinality = 2;
			printf("c | best-alg-selector overriden cardinality to 2, since it hadn't been set by the user |\n");	
		}
		
		if (!satlikeInvsThr.is_set_by_user())
		{
			Torc::Instance()->SetSatlikeInvsThr(5);
			printf("c | best-alg-selector overriden satlikeInvsThr to 5, since it hadn't been set by the user |\n");	
		}
		
		S = new OBV(verbosity, cardinality, num_conflicts, num_iterations, (bool)local); 
		algorithm = _ALGORITHM_LSU_MRSBEAVER_;  
      } else {
		  		  
        // Weighted        
        if (!satlikeTimeThr.is_set_by_user())
		{
			Torc::Instance()->SetSatlikeTimeThr(30);
			printf("c | best-alg-selector overriden satlikeTimeThr to 30 in Weighted mode, since it hadn't been set by the user |\n");	
		}
#ifdef USE_TOPOR
		Torc::Instance()->toporParams.insert(Torc::Instance()->toporParams.begin(), make_pair("/mode/value", 5));	
        printf("c | best-alg-selector overriden /topor/mode/value to 5, since we are in Weighted Topor mode |\n");	                 
#endif	

		//DoubleOption msModelPerSecThr("TTOpenWboInc", "ms_model_per_sec_thr", "Stop mutation-optimization forever when the improving models-per-second threshold is too low. If non-0, ms_sat_calls_per_iteration is not taken into account for any iteration where ms_model_per_sec_thr is considered", 0, DoubleRange(0, true, HUGE_VAL, true));
		if (!msModelPerSecThr.is_set_by_user())
        {
#ifndef USE_TOPOR			
			Torc::Instance()->SetMsModelPerSecThr(0);
			printf("c | best-alg-selector overriden ms_model_per_sec_thr to 0, since it hadn't been set by the user |\n");	
#else
			Torc::Instance()->SetMsModelPerSecThr(0.25);
			printf("c | best-alg-selector overriden ms_model_per_sec_thr to 0.25, since it hadn't been set by the user |\n");	
#endif
		}
		//DoubleOption msPropPerModelThr("TTOpenWboInc", "ms_prop_per_model_thr", "Stop mutation-optimization forever when the improving propagation-per-model threshold is too high. If non-0, ms_sat_calls_per_iteration is not taken into account for any iteration where ms_model_per_sec_conf is considered", 1000000, DoubleRange(0, true, HUGE_VAL, true));
		if (!msPropPerModelThr.is_set_by_user())
        {
			Torc::Instance()->SetMsPropPerModelThr(100000000);
			printf("c | best-alg-selector overriden ms_prop_per_model_thr to 100000000, since it hadn't been set by the user |\n");	
		}

        // S = new OLL(_VERBOSITY_MINIMAL_, cardinality);
        
        S = new LinearSUClustering(verbosity, bmo, cardinality, pb,
                                 ClusterAlg::_DIVISIVE_, rounding_statistic,
                                 (int)(num_clusters));   
        algorithm = _ALGORITHM_LSU_CLUSTER_;  
    
      }
    }

    if (S->getMaxSATFormula() == NULL) {
      S->loadFormula(maxsat_formula);
      if ((int)(cluster_algorithm) == 1) {
        switch ((int)algorithm) {
        case _ALGORITHM_LINEAR_SU_:
          static_cast<LinearSUMod *>(S)->initializeCluster();
          break;
        case _ALGORITHM_OLL_:
          static_cast<OLLMod *>(S)->initializeCluster();
          break;
        case _ALGORITHM_LSU_CLUSTER_:
          static_cast<LinearSUClustering *>(S)->initializeCluster();
          break;
        }
      }
    }
    S->setPrintModel(printmodel);
    S->setInitialTime(initial_time);
    mxsolver = S;
    mxsolver->search();

  } catch (OutOfMemoryException &) {
    sleep(1);
    printf("c Error: Out of memory.\n");
    mxsolver->printAnswer(_UNKNOWN_);
    exit(_UNKNOWN_);
  }
}
