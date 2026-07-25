#pragma once

#include <stdio.h>
#include <stdlib.h>
#include <sys/times.h>  //these two h files are for timing in linux
#include <unistd.h>

#include <chrono>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <queue>
#include <sstream>

#include "../logging/Logger.h"

using namespace std;
using namespace Aperture;

#ifndef NUWLS_MACROS_DEFINED
#define NUWLS_MACROS_DEFINED
#define mypop(stack) stack[--stack##_fill_pointer]
#define mypush(item, stack) stack[stack##_fill_pointer++] = item

const float MY_RAND_MAX_FLOAT = 10000000.0;
const int MY_RAND_MAX_INT = 10000000;
const float BASIC_SCALE = 0.0000001;
#endif

namespace nuwls {

const int USING_NEIGHBOR_MODE = 3;  // 1. using 2. don't use 3. depends on ins

struct clauselit {
  int var_num;  // variable num, begin with 1
  bool sense;   // is 1 for true literals, 0 for false literals.
};

struct varlit {
  int clause_num;  // clause num, begin with 0
  bool sense;      // is 1 for true literals, 0 for false literals.
};

static struct tms nuwls_start_time;
static double nuwls_get_runtime() {
  struct tms stop;
  times(&stop);
  return (double)(stop.tms_utime - nuwls_start_time.tms_utime + stop.tms_stime -
                  nuwls_start_time.tms_stime) /
         sysconf(_SC_CLK_TCK);
}
static void nuwls_start_timing() { times(&nuwls_start_time); }

class NUWLS {
 public:
  /***********non-algorithmic information ****************/
  int problem_weighted;
  int partial;  // 1 if the instance has hard clauses, and 0 otherwise.
  int pure_sat;

  int max_clause_length;
  int min_clause_length;

  // size of the instance
  int num_vars;     // var index from 1 to num_vars
  int num_clauses;  // clause index from 0 to num_clauses-1
  int num_hclauses;
  int num_sclauses;

  // steps and time
  int tries;
  unsigned long long max_flips;
  unsigned long long max_non_improve_flip;
  unsigned long long step;

  int print_time;
  int cutoff_time;
  int prioup_time;
  double opt_time;

  /**********end non-algorithmic information*****************/
  /* literal arrays */
  varlit **var_lit;    // var_lit[i][j] means the j'th literal of var i.
  int *var_lit_count;  // amount of literals of each var
  clauselit *
      *clause_lit;  // clause_lit[i][j] means the j'th literal of clause i.
  int *clause_lit_count;  // amount of literals in each clause

  /* Information about the variables. */
  double *score;
  int *time_stamp;
  int **var_neighbor;
  int *var_neighbor_count;
  int *neighbor_flag = NULL;
  int *temp_neighbor = NULL;
  bool if_using_neighbor = false;

  /* Information about the clauses */
  unsigned long long top_clause_weight;
  unsigned long long *org_clause_weight;
  long long total_soft_weight;
  double *clause_weight;
  int *sat_count;
  int *sat_var;
  int *best_soft_clause = NULL;

  // original unit clause stack
  // lit *unit_clause;
  int unit_clause_count;

  // unsat clauses stack
  int *hardunsat_stack;           // store the unsat clause number
  int *index_in_hardunsat_stack;  // which position is a clause in the
                                  // unsat_stack
  int hardunsat_stack_fill_pointer;

  int *softunsat_stack;           // store the unsat clause number
  int *index_in_softunsat_stack;  // which position is a clause in the
                                  // unsat_stack
  int softunsat_stack_fill_pointer;

  // variables in unsat clauses
  int *unsatvar_stack;
  int unsatvar_stack_fill_pointer;
  int *index_in_unsatvar_stack;
  int *unsat_app_count = NULL;  // a varible appears in how many unsat clauses

  // good decreasing variables (dscore>0 and confchange=1)
  int *goodvar_stack;
  int goodvar_stack_fill_pointer;
  int *already_in_goodvar_stack;
  int *score_change_stack = NULL;
  int score_change_stack_fill_pointer;
  bool *if_score_change = NULL;

  /* Information about solution */
  int *cur_soln;  // the current solution, with 1's for True variables, and 0's
                  // for False variables
  int *best_soln;
  int *local_opt_soln = NULL;
  int best_soln_feasible;  // when find a feasible solution, this is marked
                           // as 1.
  int local_soln_feasible;
  int hard_unsat_nb;
  unsigned long long soft_unsat_weight;
  unsigned long long opt_unsat_weight;
  unsigned long long local_opt_unsat_weight;

  // clause weighting
  int *large_weight_clauses;
  int large_weight_clauses_count;
  int large_clause_count_threshold;

  int *soft_large_weight_clauses;
  int *already_in_soft_large_weight_stack;
  int soft_large_weight_clauses_count;
  int soft_large_clause_count_threshold;

  // tem data structure used in algorithm
  int *best_array = NULL;
  int best_count;
  int *temp_lit = NULL;

  // parameters used in algorithm
  float rwprob;
  float rdprob;
  float smooth_probability;
  int hd_count_threshold;
  double h_inc;
  double softclause_weight_threshold;

  // clause weight tuned
  int coe_soft_clause_weight;
  double *tuned_org_clause_weight;
  double coe_tuned_weight;
  float soft_smooth_probability;
  double s_inc;
  long long total_soft_length;
  int NUWLS_TIME_LIMIT;

  // function used in algorithm
  void build_neighbor_relation();
  void allocate_memory();
  bool verify_sol();
  bool verify_goodvarstack(int flipvar);
  void smooth_weights();
  void hard_smooth_weights();
  void soft_smooth_weights();
  void hard_increase_weights();
  void soft_increase_weights();
  void update_clause_weights();
  void unsat(int clause);
  void sat(int clause);
  void init(vector<int> &init_solution);
  void flip(int flipvar);
  void flip2(int flipvar);
  void update_goodvarstack1(int flipvar);
  void update_goodvarstack2(int flipvar);
  int pick_var();
  long long floorToPowerOfTen(double x);
  long long closestPowerOfTen(double num);

  void soft_increase_weights_partial();
  void soft_increase_weights_not_partial();
  int *soft_clause_num_index;

  NUWLS();
  void settings(unsigned long long max_flips_to_set,
                unsigned long long max_non_improve_flip_to_set);
  void build_instance(char *filename);
  void build_instance(int numVars, int numClauses,
                      unsigned long long topClauseweight,
                      clauselit **nuwls_clause, int *nuwls_clause_lit_count,
                      unsigned long long *nuwls_clause_weight);
  void simple_print();
  void print_best_solution();
  void free_memory();

 private:
  Logger &logger_ = Logger::Instance();
};

inline NUWLS::NUWLS() {}

inline long long NUWLS::closestPowerOfTen(double num) {
  if (num <= 1) return 1;

  int n = ceil(log10(num));
  int x = round(num / pow(10, n - 1));

  if (x == 10) {
    x = 1;
    n += 1;
  }
  return pow(10, n - 1) * x;
}

inline long long NUWLS::floorToPowerOfTen(double x) {
  if (x <= 0.0) {
    return 0;
  }
  int exponent = (int)log10(x);
  double powerOfTen = pow(10, exponent);
  long long result = (long long)powerOfTen;
  if (x < result) {
    result /= 10;
  }
  return result;
}

inline void NUWLS::settings(
    unsigned long long max_flips_to_set = 10000000,
    unsigned long long max_non_improve_flip_to_set = 10000000) {
  local_soln_feasible = 1;
  NUWLS_TIME_LIMIT = 15;

  max_flips = max_flips_to_set;
  max_non_improve_flip = max_non_improve_flip_to_set;
  logger_.Log(VerbosityLevel::VVERBOSE,
              "max_flips = {} ; max_non_improve_flip = {}", max_flips,
              max_non_improve_flip);

  if (1 == problem_weighted) {
    logger_.Log(VerbosityLevel::VVERBOSE, "problem weighted = 1");
    large_clause_count_threshold = 0;
    soft_large_clause_count_threshold = 0;

    if (num_hclauses > 0) {
      NUWLS_TIME_LIMIT = 20;
      h_inc = 5;
      s_inc = 6;
      hd_count_threshold = 50;
      rdprob = 0.036;
      rwprob = 0.48;
      soft_smooth_probability = 2E-6;
      smooth_probability = 2E-5;
      softclause_weight_threshold = 50;

      coe_tuned_weight =
          1.0 / (double(top_clause_weight - 1) / (double)(num_sclauses));
      for (int c = 0; c < num_clauses; c++) {
        if (org_clause_weight[c] != top_clause_weight) {
          tuned_org_clause_weight[c] =
              (double)org_clause_weight[c] * coe_tuned_weight;
        }
      }
    } else {
      softclause_weight_threshold = 10;
      s_inc = 3.0;
      NUWLS_TIME_LIMIT = 25;
      soft_smooth_probability = 1E-3;
      hd_count_threshold = 22;
      rdprob = 0.036;
      rwprob = 0.48;

      coe_soft_clause_weight = 1000;
      coe_tuned_weight =
          ((double)coe_soft_clause_weight) /
          ((double(top_clause_weight - 1) / (double)(num_sclauses)));
      for (int c = 0; c < num_clauses; c++) {
        tuned_org_clause_weight[c] = org_clause_weight[c] * coe_tuned_weight;
      }
    }
  } else {
    logger_.Log(VerbosityLevel::VVERBOSE, "problem weighted = 0");

    large_clause_count_threshold = 0;
    soft_large_clause_count_threshold = 0;

    h_inc = 1;
    s_inc = 1;

    if (num_hclauses > 0) {
      hd_count_threshold = 50;
      coe_soft_clause_weight = 1;
      rdprob = 0.079;
      rwprob = 0.087;
      soft_smooth_probability = 1E-5;
      softclause_weight_threshold = 500;
      smooth_probability = 1E-4;
    } else {
      s_inc = 1;
      NUWLS_TIME_LIMIT = 15;
      hd_count_threshold = 94;
      coe_soft_clause_weight = 397;
      rdprob = 0.007;
      rwprob = 0.047;
      soft_smooth_probability = 0.002;
      softclause_weight_threshold = 550;
    }
  }
}

inline void NUWLS::allocate_memory() {
  int malloc_var_length = num_vars + 5;
  int malloc_clause_length = num_clauses + 5;
  int i = 0;

  var_lit = new varlit *[malloc_var_length];
  var_lit_count = new int[malloc_var_length];
  score = new double[malloc_var_length];
  var_neighbor = new int *[malloc_var_length];
  for (i = 0; i < malloc_var_length; i++) {
    var_lit[i] = NULL;
    var_neighbor[i] = NULL;
    var_lit_count[i] = 0;
  }
  var_neighbor_count = new int[malloc_var_length];
  time_stamp = new int[malloc_var_length];
  neighbor_flag = new int[malloc_var_length];
  temp_neighbor = new int[malloc_var_length];

  clause_weight = new double[malloc_clause_length];
  sat_count = new int[malloc_clause_length];
  sat_var = new int[malloc_clause_length];

  hardunsat_stack = new int[malloc_clause_length];
  index_in_hardunsat_stack = new int[malloc_clause_length];
  softunsat_stack = new int[malloc_clause_length];
  index_in_softunsat_stack = new int[malloc_clause_length];

  unsatvar_stack = new int[malloc_var_length];
  index_in_unsatvar_stack = new int[malloc_var_length];

  goodvar_stack = new int[malloc_var_length];
  already_in_goodvar_stack = new int[malloc_var_length];

  cur_soln = new int[malloc_var_length];
  best_soln = new int[malloc_var_length];

  large_weight_clauses = new int[malloc_clause_length];
  soft_large_weight_clauses = new int[malloc_clause_length];
  already_in_soft_large_weight_stack = new int[malloc_clause_length];
  soft_clause_num_index = new int[malloc_clause_length];

  tuned_org_clause_weight = new double[malloc_clause_length];
}

inline void NUWLS::free_memory() {
  int i;
  for (i = 0; i < num_clauses; i++) delete[] clause_lit[i];

  for (i = 1; i <= num_vars; ++i) {
    delete[] var_lit[i];
    if (var_neighbor[i] != NULL) delete[] var_neighbor[i];
  }

  delete[] var_lit;
  delete[] var_lit_count;
  delete[] clause_lit;
  delete[] clause_lit_count;

  delete[] score;
  delete[] var_neighbor;
  delete[] var_neighbor_count;
  delete[] time_stamp;
  delete[] neighbor_flag;
  delete[] temp_neighbor;

  delete[] org_clause_weight;
  delete[] clause_weight;
  delete[] sat_count;
  delete[] sat_var;

  delete[] hardunsat_stack;
  delete[] index_in_hardunsat_stack;
  delete[] softunsat_stack;
  delete[] index_in_softunsat_stack;

  delete[] unsatvar_stack;
  delete[] index_in_unsatvar_stack;

  delete[] goodvar_stack;
  delete[] already_in_goodvar_stack;

  delete[] cur_soln;
  delete[] best_soln;

  delete[] large_weight_clauses;
  delete[] soft_large_weight_clauses;
  delete[] already_in_soft_large_weight_stack;

  delete[] soft_clause_num_index;
  delete[] tuned_org_clause_weight;
}

inline void NUWLS::build_neighbor_relation() {
  int i, j, count;
  int v, c, n;
  int temp_neighbor_count;

  for (v = 1; v <= num_vars; ++v) {
    neighbor_flag[v] = 1;
    temp_neighbor_count = 0;

    for (i = 0; i < var_lit_count[v]; ++i) {
      c = var_lit[v][i].clause_num;
      for (j = 0; j < clause_lit_count[c]; ++j) {
        n = clause_lit[c][j].var_num;
        if (neighbor_flag[n] != 1) {
          neighbor_flag[n] = 1;
          temp_neighbor[temp_neighbor_count++] = n;
        }
      }
    }

    neighbor_flag[v] = 0;

    var_neighbor[v] = new int[temp_neighbor_count];
    var_neighbor_count[v] = temp_neighbor_count;

    count = 0;
    for (i = 0; i < temp_neighbor_count; i++) {
      var_neighbor[v][count++] = temp_neighbor[i];
      neighbor_flag[temp_neighbor[i]] = 0;
    }
  }
}

inline void NUWLS::build_instance(char *filename) {
  logger_.Log(VerbosityLevel::VVERBOSE, "org build instance function");
}

inline void NUWLS::build_instance(int numVars, int numClauses,
                                  unsigned long long topClauseweight,
                                  clauselit **nuwls_clause,
                                  int *nuwls_clause_lit_count,
                                  unsigned long long *nuwls_clause_weight) {
  istringstream iss;
  string line;

  nuwls_start_timing();
  total_soft_length = 0;
  num_vars = numVars;
  num_clauses = numClauses;
  top_clause_weight = topClauseweight;
  clause_lit = nuwls_clause;
  clause_lit_count = nuwls_clause_lit_count;
  org_clause_weight = nuwls_clause_weight;

  allocate_memory();
  int v;

  partial = 0;
  num_hclauses = num_sclauses = 0;
  max_clause_length = 0;
  min_clause_length = 100000000;
  unit_clause_count = 0;
  long long total_lit_count = 0;
  for (int i = 0; i < num_clauses; ++i) {
    for (int j = 0; j < clause_lit_count[i]; ++j) {
      var_lit_count[clause_lit[i][j].var_num]++;
    }

    if (org_clause_weight[i] != top_clause_weight) {
      total_soft_weight += org_clause_weight[i];
      soft_clause_num_index[num_sclauses++] = i;
    } else {
      num_hclauses++;
      partial = 1;
    }
    total_lit_count += clause_lit_count[i];
  }

  total_lit_count = 0;
  for (v = 1; v <= num_vars; ++v) {
    var_lit[v] = new varlit[var_lit_count[v] + 1];
    total_lit_count += (var_lit_count[v] + 1);
    var_lit_count[v] = 0;
  }
  for (int i = 0; i < num_clauses; ++i) {
    for (int j = 0; j < clause_lit_count[i]; ++j) {
      v = clause_lit[i][j].var_num;
      var_lit[v][var_lit_count[v]].clause_num = i;
      var_lit[v][var_lit_count[v]].sense = clause_lit[i][j].sense;
      ++var_lit_count[v];
    }
  }

  logger_.Log(VerbosityLevel::VVERBOSE, "before build neighbor");

  for (v = 1; v <= num_vars; ++v) var_lit[v][var_lit_count[v]].clause_num = -1;

  logger_.Log(VerbosityLevel::VVERBOSE, "build instime is {}",
              nuwls_get_runtime());

  if (USING_NEIGHBOR_MODE == 2 || 1 == problem_weighted ||
      (USING_NEIGHBOR_MODE == 3 &&
       ((nuwls_get_runtime() > 1.0 || num_clauses > 10000000) &&
        0 == problem_weighted))) {
    if_using_neighbor = false;
  } else {
    logger_.Log(VerbosityLevel::VVERBOSE, "using neighbor");
    if_using_neighbor = true;
    build_neighbor_relation();
  }

  best_soln_feasible = 0;
  opt_unsat_weight = total_soft_weight + 1;
}

inline void NUWLS::init(vector<int> &init_solution) {
  soft_large_weight_clauses_count = 0;
  if (1 == problem_weighted) {
    if (num_hclauses > 0) {
      for (int c = 0; c < num_clauses; c++) {
        already_in_soft_large_weight_stack[c] = 0;

        if (org_clause_weight[c] == top_clause_weight)
          clause_weight[c] = 1;
        else {
          clause_weight[c] = 0;
        }
      }
    } else {
      for (int c = 0; c < num_clauses; c++) {
        already_in_soft_large_weight_stack[c] = 0;
        clause_weight[c] = tuned_org_clause_weight[c];
        if (clause_weight[c] > s_inc &&
            already_in_soft_large_weight_stack[c] == 0) {
          already_in_soft_large_weight_stack[c] = 1;
          soft_large_weight_clauses[soft_large_weight_clauses_count++] = c;
        }
      }
    }
  } else {
    if (num_hclauses > 0) {
      for (int c = 0; c < num_clauses; c++) {
        clause_weight[c] = 1;
      }
    } else {
      for (int c = 0; c < num_clauses; c++) {
        already_in_soft_large_weight_stack[c] = 0;

        clause_weight[c] = coe_soft_clause_weight;
        if (clause_weight[c] > 1 &&
            already_in_soft_large_weight_stack[c] == 0) {
          already_in_soft_large_weight_stack[c] = 1;
          soft_large_weight_clauses[soft_large_weight_clauses_count++] = c;
        }
      }
    }
  }

  if (init_solution.size() == 0) {
    for (int v = 1; v <= num_vars; v++) {
      cur_soln[v] = rand() % 2;
      time_stamp[v] = 0;
    }
  } else {
    for (int v = 1; v <= num_vars; v++) {
      cur_soln[v] = init_solution[v];
      time_stamp[v] = 0;
    }
  }
  local_soln_feasible = 0;
  hard_unsat_nb = 0;
  soft_unsat_weight = 0;
  hardunsat_stack_fill_pointer = 0;
  softunsat_stack_fill_pointer = 0;
  unsatvar_stack_fill_pointer = 0;
  large_weight_clauses_count = 0;

  for (int c = 0; c < num_clauses; ++c) {
    sat_count[c] = 0;
    for (int j = 0; j < clause_lit_count[c]; ++j) {
      if (cur_soln[clause_lit[c][j].var_num] == clause_lit[c][j].sense) {
        sat_count[c]++;
        sat_var[c] = clause_lit[c][j].var_num;
      }
    }
    if (sat_count[c] == 0) {
      unsat(c);
    }
  }

  for (int v = 1; v <= num_vars; v++) {
    score[v] = 0.0;
    for (int i = 0; i < var_lit_count[v]; ++i) {
      int c = var_lit[v][i].clause_num;
      if (sat_count[c] == 0)
        score[v] += clause_weight[c];
      else if (sat_count[c] == 1 && var_lit[v][i].sense == cur_soln[v])
        score[v] -= clause_weight[c];
    }
  }

  goodvar_stack_fill_pointer = 0;
  score_change_stack_fill_pointer = 0;
  for (int v = 1; v <= num_vars; v++) {
    if (score[v] > 0) {
      already_in_goodvar_stack[v] = goodvar_stack_fill_pointer;
      mypush(v, goodvar_stack);
    } else
      already_in_goodvar_stack[v] = -1;
  }
}

inline void NUWLS::smooth_weights() {
  int i, clause, v;

  for (i = 0; i < large_weight_clauses_count; i++) {
    clause = large_weight_clauses[i];
    if (sat_count[clause] > 0) {
      clause_weight[clause] -= h_inc;

      if (clause_weight[clause] == 1) {
        large_weight_clauses[i] =
            large_weight_clauses[--large_weight_clauses_count];
        i--;
      }
      if (sat_count[clause] == 1) {
        v = sat_var[clause];
        score[v] += h_inc;
        if (score[v] > 0 && already_in_goodvar_stack[v] == -1) {
          already_in_goodvar_stack[v] = goodvar_stack_fill_pointer;
          mypush(v, goodvar_stack);
        }
      }
    }
  }

  for (i = 0; i < soft_large_weight_clauses_count; i++) {
    clause = soft_large_weight_clauses[i];
    if (sat_count[clause] > 0) {
      clause_weight[clause]--;
      if (clause_weight[clause] == 1 &&
          already_in_soft_large_weight_stack[clause] == 1) {
        already_in_soft_large_weight_stack[clause] = 0;
        soft_large_weight_clauses[i] =
            soft_large_weight_clauses[--soft_large_weight_clauses_count];
        i--;
      }
      if (sat_count[clause] == 1) {
        v = sat_var[clause];
        score[v]++;
        if (score[v] > 0 && already_in_goodvar_stack[v] == -1) {
          already_in_goodvar_stack[v] = goodvar_stack_fill_pointer;
          mypush(v, goodvar_stack);
        }
      }
    }
  }
}

inline void NUWLS::hard_increase_weights() {
  int i, c, v;
  for (i = 0; i < hardunsat_stack_fill_pointer; ++i) {
    c = hardunsat_stack[i];

    clause_weight[c] += h_inc;

    if (clause_weight[c] == (h_inc + 1))
      large_weight_clauses[large_weight_clauses_count++] = c;

    for (clauselit *p = clause_lit[c]; (v = p->var_num) != 0; p++) {
      score[v] += h_inc;
      if (score[v] > 0 && already_in_goodvar_stack[v] == -1) {
        already_in_goodvar_stack[v] = goodvar_stack_fill_pointer;
        mypush(v, goodvar_stack);
      }
    }
  }
  return;
}

inline void NUWLS::soft_increase_weights() {
  int i, c, v;

  if (1 == problem_weighted) {
    for (i = 0; i < softunsat_stack_fill_pointer; ++i) {
      c = softunsat_stack[i];
      if (clause_weight[c] >=
          tuned_org_clause_weight[c] + softclause_weight_threshold)
        continue;
      else
        clause_weight[c] += s_inc;

      if (clause_weight[c] > s_inc &&
          already_in_soft_large_weight_stack[c] == 0) {
        already_in_soft_large_weight_stack[c] = 1;
        soft_large_weight_clauses[soft_large_weight_clauses_count++] = c;
      }
      for (clauselit *p = clause_lit[c]; (v = p->var_num) != 0; p++) {
        score[v] += s_inc;
        if (score[v] > 0 && already_in_goodvar_stack[v] == -1) {
          already_in_goodvar_stack[v] = goodvar_stack_fill_pointer;
          mypush(v, goodvar_stack);
        }
      }
    }
  } else {
    for (i = 0; i < softunsat_stack_fill_pointer; ++i) {
      c = softunsat_stack[i];
      if (clause_weight[c] >=
          coe_soft_clause_weight + softclause_weight_threshold)
        continue;
      else
        clause_weight[c] += s_inc;

      if (clause_weight[c] > s_inc &&
          already_in_soft_large_weight_stack[c] == 0) {
        already_in_soft_large_weight_stack[c] = 1;
        soft_large_weight_clauses[soft_large_weight_clauses_count++] = c;
      }
      for (clauselit *p = clause_lit[c]; (v = p->var_num) != 0; p++) {
        score[v] += s_inc;
        if (score[v] > 0 && already_in_goodvar_stack[v] == -1) {
          already_in_goodvar_stack[v] = goodvar_stack_fill_pointer;
          mypush(v, goodvar_stack);
        }
      }
    }
  }

  return;
}

inline void NUWLS::hard_smooth_weights() {
  int i, clause, v;
  for (i = 0; i < large_weight_clauses_count; i++) {
    clause = large_weight_clauses[i];
    if (sat_count[clause] > 0) {
      clause_weight[clause] -= h_inc;

      if (clause_weight[clause] == 1) {
        large_weight_clauses[i] =
            large_weight_clauses[--large_weight_clauses_count];
        i--;
      }
      if (sat_count[clause] == 1) {
        v = sat_var[clause];
        score[v] += h_inc;
        if (score[v] > 0 && already_in_goodvar_stack[v] == -1) {
          already_in_goodvar_stack[v] = goodvar_stack_fill_pointer;
          mypush(v, goodvar_stack);
        }
      }
    }
  }
  return;
}

inline void NUWLS::soft_smooth_weights() {
  int i, clause, v;

  for (i = 0; i < soft_large_weight_clauses_count; i++) {
    clause = soft_large_weight_clauses[i];
    if (sat_count[clause] > 0) {
      clause_weight[clause] -= s_inc;
      if (clause_weight[clause] <= s_inc &&
          already_in_soft_large_weight_stack[clause] == 1) {
        already_in_soft_large_weight_stack[clause] = 0;
        soft_large_weight_clauses[i] =
            soft_large_weight_clauses[--soft_large_weight_clauses_count];
        i--;
      }
      if (sat_count[clause] == 1) {
        v = sat_var[clause];
        score[v] += s_inc;
        if (score[v] > 0 && already_in_goodvar_stack[v] == -1) {
          already_in_goodvar_stack[v] = goodvar_stack_fill_pointer;
          mypush(v, goodvar_stack);
        }
      }
    }
  }
  return;
}

inline void NUWLS::soft_increase_weights_partial() {
  int i, c, v;

  if (1 == problem_weighted) {
    for (i = 0; i < num_sclauses; ++i) {
      c = soft_clause_num_index[i];
      clause_weight[c] += tuned_org_clause_weight[c];
      if (sat_count[c] <= 0) {
        for (clauselit *p = clause_lit[c]; (v = p->var_num) != 0; p++) {
          score[v] += tuned_org_clause_weight[c];
          if (score[v] > 0 && already_in_goodvar_stack[v] == -1) {
            already_in_goodvar_stack[v] = goodvar_stack_fill_pointer;
            mypush(v, goodvar_stack);
          }
        }
      } else if (sat_count[c] < 2) {
        for (clauselit *p = clause_lit[c]; (v = p->var_num) != 0; p++) {
          if (p->sense == cur_soln[v]) {
            score[v] -= tuned_org_clause_weight[c];
            if (score[v] <= 0 && -1 != already_in_goodvar_stack[v]) {
              int index = already_in_goodvar_stack[v];
              int last_v = mypop(goodvar_stack);
              goodvar_stack[index] = last_v;
              already_in_goodvar_stack[last_v] = index;
              already_in_goodvar_stack[v] = -1;
            }
          }
        }
      }
    }
  } else {
    for (i = 0; i < num_sclauses; ++i) {
      c = soft_clause_num_index[i];
      clause_weight[c] += s_inc;

      if (sat_count[c] <= 0) {
        for (clauselit *p = clause_lit[c]; (v = p->var_num) != 0; p++) {
          score[v] += s_inc;
          if (score[v] > 0 && already_in_goodvar_stack[v] == -1) {
            already_in_goodvar_stack[v] = goodvar_stack_fill_pointer;
            mypush(v, goodvar_stack);
          }
        }
      } else if (sat_count[c] < 2) {
        for (clauselit *p = clause_lit[c]; (v = p->var_num) != 0; p++) {
          if (p->sense == cur_soln[v]) {
            score[v] -= s_inc;
            if (score[v] <= 0 && -1 != already_in_goodvar_stack[v]) {
              int index = already_in_goodvar_stack[v];
              int last_v = mypop(goodvar_stack);
              goodvar_stack[index] = last_v;
              already_in_goodvar_stack[last_v] = index;
              already_in_goodvar_stack[v] = -1;
            }
          }
        }
      }
    }
  }
  return;
}

inline void NUWLS::soft_increase_weights_not_partial() {
  int i, c, v;

  if (1 == problem_weighted) {
    for (i = 0; i < softunsat_stack_fill_pointer; ++i) {
      c = softunsat_stack[i];
      if (clause_weight[c] >=
          tuned_org_clause_weight[c] + softclause_weight_threshold)
        continue;
      else
        clause_weight[c] += s_inc;

      if (clause_weight[c] > s_inc &&
          already_in_soft_large_weight_stack[c] == 0) {
        already_in_soft_large_weight_stack[c] = 1;
        soft_large_weight_clauses[soft_large_weight_clauses_count++] = c;
      }
      for (clauselit *p = clause_lit[c]; (v = p->var_num) != 0; p++) {
        score[v] += s_inc;
        if (score[v] > 0 && already_in_goodvar_stack[v] == -1) {
          already_in_goodvar_stack[v] = goodvar_stack_fill_pointer;
          mypush(v, goodvar_stack);
        }
      }
    }
  } else {
    for (i = 0; i < softunsat_stack_fill_pointer; ++i) {
      c = softunsat_stack[i];
      if (clause_weight[c] >=
          coe_soft_clause_weight + softclause_weight_threshold)
        continue;
      else
        clause_weight[c] += s_inc;

      if (clause_weight[c] > s_inc &&
          already_in_soft_large_weight_stack[c] == 0) {
        already_in_soft_large_weight_stack[c] = 1;
        soft_large_weight_clauses[soft_large_weight_clauses_count++] = c;
      }
      for (clauselit *p = clause_lit[c]; (v = p->var_num) != 0; p++) {
        score[v] += s_inc;
        if (score[v] > 0 && already_in_goodvar_stack[v] == -1) {
          already_in_goodvar_stack[v] = goodvar_stack_fill_pointer;
          mypush(v, goodvar_stack);
        }
      }
    }
  }
  return;
}

inline void NUWLS::update_clause_weights() {
  if (num_hclauses > 0) {
    hard_increase_weights();
    if (0 == hard_unsat_nb) {
      soft_increase_weights_partial();
    }
  } else {
    if (((rand() % MY_RAND_MAX_INT) * BASIC_SCALE) < soft_smooth_probability &&
        soft_large_weight_clauses_count > soft_large_clause_count_threshold) {
      soft_smooth_weights();
    } else {
      soft_increase_weights_not_partial();
    }
  }
}

inline int NUWLS::pick_var() {
  int i, v;
  int best_var;

  if (goodvar_stack_fill_pointer > 0) {
    if ((rand() % MY_RAND_MAX_INT) * BASIC_SCALE < rdprob)
      return goodvar_stack[rand() % goodvar_stack_fill_pointer];

    if (goodvar_stack_fill_pointer < hd_count_threshold) {
      best_var = goodvar_stack[0];
      for (i = 1; i < goodvar_stack_fill_pointer; ++i) {
        v = goodvar_stack[i];
        if (score[v] > score[best_var])
          best_var = v;
        else if (score[v] == score[best_var]) {
          if (time_stamp[v] < time_stamp[best_var]) best_var = v;
        }
      }
      return best_var;
    } else {
      best_var = goodvar_stack[rand() % goodvar_stack_fill_pointer];
      for (i = 1; i < hd_count_threshold; ++i) {
        v = goodvar_stack[rand() % goodvar_stack_fill_pointer];
        if (score[v] > score[best_var])
          best_var = v;
        else if (score[v] == score[best_var]) {
          if (time_stamp[v] < time_stamp[best_var]) best_var = v;
        }
      }
      return best_var;
    }
  }

  update_clause_weights();

  int sel_c;
  clauselit *p;

  if (hardunsat_stack_fill_pointer > 0) {
    sel_c = hardunsat_stack[rand() % hardunsat_stack_fill_pointer];
  } else if (softunsat_stack_fill_pointer > 0) {
    sel_c = softunsat_stack[rand() % softunsat_stack_fill_pointer];
  } else {
    return 0;
  }
  if ((rand() % MY_RAND_MAX_INT) * BASIC_SCALE < rwprob)
    return clause_lit[sel_c][rand() % clause_lit_count[sel_c]].var_num;

  best_var = clause_lit[sel_c][0].var_num;
  p = clause_lit[sel_c];
  for (p++; (v = p->var_num) != 0; p++) {
    if (score[v] > score[best_var])
      best_var = v;
    else if (score[v] == score[best_var]) {
      if (time_stamp[v] < time_stamp[best_var]) best_var = v;
    }
  }

  return best_var;
}

inline void NUWLS::update_goodvarstack1(int flipvar) {
  int v;
  for (int index = goodvar_stack_fill_pointer - 1; index >= 0; index--) {
    v = goodvar_stack[index];
    if (score[v] <= 0) {
      goodvar_stack[index] = mypop(goodvar_stack);
      already_in_goodvar_stack[goodvar_stack[index]] = index;
      already_in_goodvar_stack[v] = -1;
    }
  }

  for (int i = 0; i < var_neighbor_count[flipvar]; ++i) {
    v = var_neighbor[flipvar][i];
    if (score[v] > 0 && already_in_goodvar_stack[v] == -1) {
      already_in_goodvar_stack[v] = goodvar_stack_fill_pointer;
      mypush(v, goodvar_stack);
    }
  }
}

inline void NUWLS::flip(int flipvar) {
  int i, v, c, clen = 0;
  int index;
  clauselit *clause_c;
  score_change_stack_fill_pointer = 0;
  double org_flipvar_score = score[flipvar];
  cur_soln[flipvar] = 1 - cur_soln[flipvar];

  for (i = 0; i < var_lit_count[flipvar]; ++i) {
    c = var_lit[flipvar][i].clause_num;
    clause_c = clause_lit[c];

    if (cur_soln[flipvar] == var_lit[flipvar][i].sense) {
      ++sat_count[c];
      if (sat_count[c] == 2) {
        v = sat_var[c];
        score[v] += clause_weight[c];
        if (score[v] > 0 && -1 == already_in_goodvar_stack[v]) {
          already_in_goodvar_stack[v] = goodvar_stack_fill_pointer;
          mypush(v, goodvar_stack);
        }
      } else if (sat_count[c] == 1) {
        sat_var[c] = flipvar;
        for (clen = 0; clen < clause_lit_count[c]; clen++) {
          v = clause_lit[c][clen].var_num;
          score[v] -= clause_weight[c];
          if (score[v] <= 0 && -1 != already_in_goodvar_stack[v]) {
            int index = already_in_goodvar_stack[v];
            int last_v = mypop(goodvar_stack);
            goodvar_stack[index] = last_v;
            already_in_goodvar_stack[last_v] = index;
            already_in_goodvar_stack[v] = -1;
          }
        }
        sat(c);
      }
    } else {
      --sat_count[c];
      if (sat_count[c] == 1) {
        for (clen = 0; clen < clause_lit_count[c]; clen++) {
          v = clause_lit[c][clen].var_num;
          if (clause_lit[c][clen].sense == cur_soln[v]) {
            score[v] -= clause_weight[c];
            if (score[v] <= 0 && -1 != already_in_goodvar_stack[v]) {
              int index = already_in_goodvar_stack[v];
              int last_v = mypop(goodvar_stack);
              goodvar_stack[index] = last_v;
              already_in_goodvar_stack[last_v] = index;
              already_in_goodvar_stack[v] = -1;
            }
            sat_var[c] = v;
            break;
          }
        }
      } else if (sat_count[c] == 0) {
        for (clen = 0; clen < clause_lit_count[c]; clen++) {
          v = clause_lit[c][clen].var_num;
          score[v] += clause_weight[c];
          if (score[v] > 0 && -1 == already_in_goodvar_stack[v]) {
            already_in_goodvar_stack[v] = goodvar_stack_fill_pointer;
            mypush(v, goodvar_stack);
          }
        }
        unsat(c);
      }
    }
  }

  score[flipvar] = -org_flipvar_score;
  if (score[flipvar] > 0 && already_in_goodvar_stack[flipvar] == -1) {
    already_in_goodvar_stack[flipvar] = goodvar_stack_fill_pointer;
    mypush(flipvar, goodvar_stack);
  } else if (score[flipvar] <= 0 && already_in_goodvar_stack[flipvar] != -1) {
    int index = already_in_goodvar_stack[flipvar];
    int last_v = mypop(goodvar_stack);
    goodvar_stack[index] = last_v;
    already_in_goodvar_stack[last_v] = index;
    already_in_goodvar_stack[flipvar] = -1;
  }
}

inline void NUWLS::flip2(int flipvar) {
  int i, v, c;
  int index;
  clauselit *clause_c;

  score_change_stack_fill_pointer = 0;
  double org_flipvar_score = score[flipvar];
  cur_soln[flipvar] = 1 - cur_soln[flipvar];

  for (i = 0; i < var_lit_count[flipvar]; ++i) {
    c = var_lit[flipvar][i].clause_num;
    clause_c = clause_lit[c];

    if (cur_soln[flipvar] == var_lit[flipvar][i].sense) {
      ++sat_count[c];
      if (sat_count[c] == 2) {
        score[sat_var[c]] += clause_weight[c];
      } else if (sat_count[c] == 1) {
        sat_var[c] = flipvar;
        for (clauselit *p = clause_c; (v = p->var_num) != 0; p++) {
          score[v] -= clause_weight[c];
        }
        sat(c);
      }
    } else {
      --sat_count[c];
      if (sat_count[c] == 1) {
        for (clauselit *p = clause_c; (v = p->var_num) != 0; p++) {
          if (p->sense == cur_soln[v]) {
            score[v] -= clause_weight[c];
            sat_var[c] = v;
            break;
          }
        }
      } else if (sat_count[c] == 0) {
        for (clauselit *p = clause_c; (v = p->var_num) != 0; p++) {
          score[v] += clause_weight[c];
        }
        unsat(c);
      }
    }
  }

  score[flipvar] = -org_flipvar_score;
  update_goodvarstack1(flipvar);
}

inline void NUWLS::print_best_solution() {
  if (best_soln_feasible == 0) return;

  printf("v");
  for (int i = 1; i <= num_vars; i++) {
    printf(" ");
    if (best_soln[i] == 0) printf("-");
    printf("%d", i);
  }
  printf("\n");
}

inline bool NUWLS::verify_sol() {
  int c, j, flag;
  unsigned long long verify_unsat_weight = 0;

  for (c = 0; c < num_clauses; ++c) {
    flag = 0;
    for (j = 0; j < clause_lit_count[c]; ++j) {
      if (cur_soln[clause_lit[c][j].var_num] == clause_lit[c][j].sense) {
        flag = 1;
        break;
      }
    }
    if (flag == 0) {
      if (org_clause_weight[c] == top_clause_weight) {
        logger_.Log(VerbosityLevel::VERBOSE,
                    "Error: hard clause {} is not satisfied", c);

        string clause_str;

        for (j = 0; j < clause_lit_count[c]; ++j) {
          if (clause_lit[c][j].sense == 0) clause_str += "-";
          clause_str += to_string(clause_lit[c][j].var_num) + " \n";
        }
        logger_.Log(VerbosityLevel::VERBOSE, "{}", clause_str);

        string soln_str;
        for (j = 0; j < clause_lit_count[c]; ++j)
          soln_str += (cur_soln[clause_lit[c][j].var_num] + " ");
        logger_.Log(VerbosityLevel::VERBOSE, "{}", soln_str);
        return 0;
      } else {
        verify_unsat_weight += org_clause_weight[c];
      }
    }
  }

  if (verify_unsat_weight == opt_unsat_weight) {
    logger_.Log(VerbosityLevel::VERBOSE, "yes {}", verify_unsat_weight);
  } else {
    logger_.Log(VerbosityLevel::VERBOSE,
                "Error: find opt={} , but verified opt={}", opt_unsat_weight,
                verify_unsat_weight);
  }
  return 0;
}

inline bool NUWLS::verify_goodvarstack(int flipvar) {
  for (int i = 1; i <= num_vars; ++i) {
    if (i == flipvar) continue;
    if (score[i] > 0 && already_in_goodvar_stack[i] == -1) {
      logger_.Log(VerbosityLevel::VERBOSE, "wrong 1 :");
      logger_.Log(VerbosityLevel::VERBOSE, "var is {}", i);
    } else if (score[i] <= 0 && already_in_goodvar_stack[i] != -1) {
      logger_.Log(VerbosityLevel::VERBOSE, "wrong 2 :");
      logger_.Log(VerbosityLevel::VERBOSE, "var is {}", i);
    }
  }
  if (score[flipvar] > 0 && already_in_goodvar_stack[flipvar] != -1) {
    logger_.Log(VerbosityLevel::VERBOSE, "wrong flipvar in good var {}",
                flipvar);
    logger_.Log(VerbosityLevel::VERBOSE, "{}", score[flipvar]);
  }
  return 1;
}

inline void NUWLS::simple_print() {
  if (best_soln_feasible == 1) {
    if (verify_sol() == 1)
      logger_.Log(VerbosityLevel::VERBOSE, "{} \t {}", opt_unsat_weight,
                  opt_time);
    else
      logger_.Log(VerbosityLevel::VERBOSE, "solution is wrong ");
  } else
    logger_.Log(VerbosityLevel::VERBOSE, "{}\t{}", -1, -1);
}

inline void NUWLS::unsat(int clause) {
  if (org_clause_weight[clause] == top_clause_weight) {
    index_in_hardunsat_stack[clause] = hardunsat_stack_fill_pointer;
    mypush(clause, hardunsat_stack);
    hard_unsat_nb++;
  } else {
    index_in_softunsat_stack[clause] = softunsat_stack_fill_pointer;
    mypush(clause, softunsat_stack);
    soft_unsat_weight += org_clause_weight[clause];
  }
}

inline void NUWLS::sat(int clause) {
  int index, last_unsat_clause;

  if (org_clause_weight[clause] == top_clause_weight) {
    last_unsat_clause = mypop(hardunsat_stack);
    index = index_in_hardunsat_stack[clause];
    hardunsat_stack[index] = last_unsat_clause;
    index_in_hardunsat_stack[last_unsat_clause] = index;

    hard_unsat_nb--;
  } else {
    last_unsat_clause = mypop(softunsat_stack);
    index = index_in_softunsat_stack[clause];
    softunsat_stack[index] = last_unsat_clause;
    index_in_softunsat_stack[last_unsat_clause] = index;

    soft_unsat_weight -= org_clause_weight[clause];
  }
}

}  // namespace nuwls
