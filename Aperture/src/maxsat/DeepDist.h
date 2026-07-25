#pragma once

#include <stdio.h>
#include <stdlib.h>
#include <sys/times.h>
#include <unistd.h>

#include <cmath>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <queue>
#include <sstream>

#include "../logging/Logger.h"

using namespace std;
using namespace Aperture;

// These are already defined in NuWLS.h, so guard them
#ifndef NUWLS_MACROS_DEFINED
#define NUWLS_MACROS_DEFINED
#define mypop(stack) stack[--stack##_fill_pointer]
#define mypush(item, stack) stack[stack##_fill_pointer++] = item

const float MY_RAND_MAX_FLOAT = 10000000.0;
const int MY_RAND_MAX_INT = 10000000;
const float BASIC_SCALE = 0.0000001;
#endif

namespace deepdist {

// DeepDist uses its own lit struct (has clause_num, unlike NuWLS's clauselit)
struct lit {
  int clause_num;  // clause num, begin with 0
  int var_num;     // variable num, begin with 1
  bool sense;      // is 1 for true literals, 0 for false literals.
};

static struct tms dd_start_time;
static double dd_get_runtime() {
  struct tms stop;
  times(&stop);
  return (double)(stop.tms_utime - dd_start_time.tms_utime + stop.tms_stime -
                  dd_start_time.tms_stime) /
         sysconf(_SC_CLK_TCK);
}
static void dd_start_timing() { times(&dd_start_time); }

class Decimation {
 public:
  Decimation(lit **ls_var_lit, int *ls_var_lit_count, lit **ls_clause_lit,
             long long *ls_org_clause_weight, long long ls_top_clause_weight);

  void make_space(int max_c, int max_v);
  void free_memory();
  void init(int *ls_local_opt, int *ls_global_opt, lit *ls_unit_clause,
            int ls_unit_clause_count, int *ls_clause_lit_count);
  void push_unit_clause_to_queue(lit tem_l);
  void assign(int v, int sense);
  void remove_unassigned_var(int v);
  void hunit_propagation();
  void sunit_propagation();
  void random_propagation();
  void unit_prosess();
  void hard_unit_prosess();
  bool choose_sense(int v);
  void hard_random_propagation();
  void remove_assigned_hard_clause(int c);

  vector<int> fix;

  int num_vars;
  int num_clauses;

  long long *h_true_score;
  long long *h_false_score;
  long long *hscore;
  long long *s_true_score;
  long long *s_false_score;
  long long *sscore;

  lit **clause_lit;
  lit **var_lit;
  int *var_lit_count;

  int *local_opt;
  int *global_opt;
  long long *org_clause_weight;
  long long top_clause_weight;

  lit *hunit_clause_queue;
  int *sense_in_hunit_clause_queue;
  int hunit_beg_pointer;
  int hunit_end_pointer;

  lit *sunit_clause_queue;
  int *sense_in_sunit_clause_queue;
  int sunit_beg_pointer;
  int sunit_end_pointer;

  int *unassigned_var;
  int *index_in_unassigned_var;
  int unassigned_var_count;

  int *clause_delete;
  int *clause_lit_count;

  int *hard_unsat_clause;
  int *index_in_hard_unsat_clause;
  int hard_unsat_clause_count;
};

inline Decimation::Decimation(lit **ls_var_lit, int *ls_var_lit_count,
                              lit **ls_clause_lit,
                              long long *ls_org_clause_weight,
                              long long ls_top_clause_weight) {
  var_lit = ls_var_lit;
  var_lit_count = ls_var_lit_count;
  clause_lit = ls_clause_lit;
  org_clause_weight = ls_org_clause_weight;
  top_clause_weight = ls_top_clause_weight;
}

inline void Decimation::make_space(int max_c, int max_v) {
  num_vars = max_v;
  num_clauses = max_c;

  max_c += 10;
  max_v += 10;

  h_true_score = new long long[max_v];
  h_false_score = new long long[max_v];
  hscore = new long long[max_v];
  s_true_score = new long long[max_v];
  s_false_score = new long long[max_v];
  sscore = new long long[max_v];

  fix.resize(max_v);
  fix.reserve(max_v);

  hunit_clause_queue = new lit[max_v];
  sense_in_hunit_clause_queue = new int[max_v];

  sunit_clause_queue = new lit[max_v];
  sense_in_sunit_clause_queue = new int[max_v];

  unassigned_var = new int[max_v];
  index_in_unassigned_var = new int[max_v];

  clause_delete = new int[max_c];
  clause_lit_count = new int[max_c];

  hard_unsat_clause = new int[max_c];
  index_in_hard_unsat_clause = new int[max_c];
}

inline void Decimation::free_memory() {
  fix.clear();
  delete[] h_true_score;
  delete[] h_false_score;
  delete[] hscore;
  delete[] s_true_score;
  delete[] s_false_score;
  delete[] sscore;

  delete[] hunit_clause_queue;
  delete[] sense_in_hunit_clause_queue;

  delete[] sunit_clause_queue;
  delete[] sense_in_sunit_clause_queue;

  delete[] unassigned_var;
  delete[] index_in_unassigned_var;

  delete[] clause_delete;
  delete[] clause_lit_count;

  delete[] hard_unsat_clause;
  delete[] index_in_hard_unsat_clause;
}

inline void Decimation::init(int *ls_local_opt, int *ls_global_opt,
                             lit *ls_unit_clause, int ls_unit_clause_count,
                             int *ls_clause_lit_count) {
  int v;
  int c;
  hunit_beg_pointer = 0;
  hunit_end_pointer = 0;

  sunit_beg_pointer = 0;
  sunit_end_pointer = 0;

  unassigned_var_count = num_vars;
  hard_unsat_clause_count = 0;

  local_opt = ls_local_opt;
  global_opt = ls_global_opt;

  for (int i = 0; i < num_vars; ++i) {
    v = i + 1;
    unassigned_var[i] = v;
    index_in_unassigned_var[v] = i;

    fix[v] = -1;
    sense_in_hunit_clause_queue[v] = -1;
    sense_in_sunit_clause_queue[v] = -1;
  }

  for (int i = 0; i < num_clauses; ++i) {
    clause_lit_count[i] = ls_clause_lit_count[i];
    clause_delete[i] = 0;

    if (org_clause_weight[i] == top_clause_weight) {
      hard_unsat_clause[hard_unsat_clause_count] = i;
      index_in_hard_unsat_clause[i] = hard_unsat_clause_count;
      ++hard_unsat_clause_count;
    }
  }

  for (int i = 0; i < ls_unit_clause_count; ++i) {
    push_unit_clause_to_queue(ls_unit_clause[i]);
  }

  for (v = 1; v <= num_vars; ++v) {
    h_false_score[v] = 0;
    h_true_score[v] = 0;
    s_false_score[v] = 0;
    s_true_score[v] = 0;
    for (int i = 0; i < var_lit_count[v]; ++i) {
      c = var_lit[v][i].clause_num;
      if (org_clause_weight[c] == top_clause_weight) {
        if (var_lit[v][i].sense == 1)
          ++h_true_score[v];
        else
          ++h_false_score[v];
      } else {
        if (var_lit[v][i].sense == 1)
          s_true_score[v] += org_clause_weight[c];
        else
          s_false_score[v] += org_clause_weight[c];
      }
    }
    hscore[v] = max(h_false_score[v], h_true_score[v]);
    sscore[v] = max(s_false_score[v], s_true_score[v]);
  }
}

inline void Decimation::push_unit_clause_to_queue(lit tem_l) {
  int v = tem_l.var_num;
  int c = tem_l.clause_num;
  if (org_clause_weight[c] == top_clause_weight) {
    if (sense_in_hunit_clause_queue[v] == -1) {
      sense_in_hunit_clause_queue[v] = tem_l.sense;
      hunit_clause_queue[hunit_end_pointer++] = tem_l;
    } else {
      if (sense_in_hunit_clause_queue[v] != (int)tem_l.sense) {
        sense_in_hunit_clause_queue[v] = -2;
      }
    }
  } else {
    if (sense_in_hunit_clause_queue[v] != -1) return;

    if (sense_in_sunit_clause_queue[v] == -1) {
      sense_in_sunit_clause_queue[v] = tem_l.sense;
      sunit_clause_queue[sunit_end_pointer++] = tem_l;
    } else {
      if (sense_in_sunit_clause_queue[v] != (int)tem_l.sense) {
        sense_in_sunit_clause_queue[v] = -3;
      }
    }
  }
}

inline void Decimation::remove_unassigned_var(int v) {
  int index = index_in_unassigned_var[v];
  int last_var = unassigned_var[--unassigned_var_count];
  unassigned_var[index] = last_var;
  index_in_unassigned_var[last_var] = index;
}

inline void Decimation::assign(int v, int sense) {
  int c;
  lit tem_lit;
  fix[v] = sense;
  remove_unassigned_var(v);

  for (int i = 0; i < var_lit_count[v]; ++i) {
    c = var_lit[v][i].clause_num;
    if (clause_delete[c] == 1) continue;

    if (sense == (int)var_lit[v][i].sense) {
      clause_delete[c] = 1;
      if (org_clause_weight[c] == top_clause_weight) {
        remove_assigned_hard_clause(c);
        for (int j = 0; j < clause_lit_count[c]; j++) {
          tem_lit = clause_lit[c][j];
          if (tem_lit.sense == 1) {
            h_true_score[tem_lit.var_num]--;
          } else
            h_false_score[tem_lit.var_num]--;
          hscore[tem_lit.var_num] = max(h_true_score[tem_lit.var_num],
                                        h_false_score[tem_lit.var_num]);
        }
      } else {
        for (int j = 0; j < clause_lit_count[c]; j++) {
          tem_lit = clause_lit[c][j];
          if (tem_lit.sense == 1) {
            s_true_score[tem_lit.var_num] -= org_clause_weight[c];
          } else
            s_false_score[tem_lit.var_num] -= org_clause_weight[c];
          sscore[tem_lit.var_num] = max(s_true_score[tem_lit.var_num],
                                        s_false_score[tem_lit.var_num]);
        }
      }
      continue;
    }

    for (int j = 0; j < clause_lit_count[c]; j++) {
      if (clause_lit[c][j].var_num == v) {
        swap(clause_lit[c][j], clause_lit[c][--clause_lit_count[c]]);
        break;
      }
    }
    if (clause_lit_count[c] == 1) {
      push_unit_clause_to_queue(clause_lit[c][0]);
    }
  }
}

inline bool Decimation::choose_sense(int v) { return rand() % 2; }

inline void Decimation::hunit_propagation() {
  int v, sense;

  v = hunit_clause_queue[hunit_beg_pointer].var_num;
  sense = hunit_clause_queue[hunit_beg_pointer].sense;
  hunit_beg_pointer++;

  if (sense_in_hunit_clause_queue[v] == -2) {
    if (sscore[v] > 0) {
      if (sscore[v] == s_true_score[v])
        sense = 1;
      else
        sense = 0;
    } else {
      sense = global_opt[v];
    }
  }
  assign(v, sense);
}

inline void Decimation::sunit_propagation() {
  int v, sense;

  int best_v = sunit_clause_queue[sunit_beg_pointer].var_num;
  long long best_score = sscore[best_v];
  int index = sunit_beg_pointer;
  int count = sunit_end_pointer - sunit_beg_pointer;

  if (count > 15) {
    for (int i = 0; i < 15; ++i) {
      int rd = rand() % count;
      v = sunit_clause_queue[sunit_beg_pointer + rd].var_num;
      if (sscore[v] > best_score) {
        best_v = v;
        best_score = sscore[v];
        index = sunit_beg_pointer + rd;
      }
    }
  } else {
    for (int i = sunit_beg_pointer; i < sunit_end_pointer; ++i) {
      v = sunit_clause_queue[i].var_num;
      if (sscore[v] > best_score) {
        best_v = v;
        best_score = sscore[v];
        index = i;
      }
    }
  }

  swap(sunit_clause_queue[sunit_beg_pointer], sunit_clause_queue[index]);
  v = sunit_clause_queue[sunit_beg_pointer].var_num;
  sense = sunit_clause_queue[sunit_beg_pointer].sense;
  sunit_beg_pointer++;

  if (fix[v] != -1) return;

  if (sense_in_sunit_clause_queue[v] == -3) {
    if (hscore[v] > 0) {
      if (hscore[v] == h_true_score[v])
        sense = 1;
      else
        sense = 0;
    } else {
      sense = global_opt[v];
    }
  }

  assign(v, sense);
}

inline void Decimation::random_propagation() {
  int v, sense;
  v = unassigned_var[rand() % unassigned_var_count];
  sense = rand() % 2;
  assign(v, sense);
}

inline void Decimation::remove_assigned_hard_clause(int c) {
  int last_unsat_clause = hard_unsat_clause[--hard_unsat_clause_count];
  int index = index_in_hard_unsat_clause[c];
  hard_unsat_clause[index] = last_unsat_clause;
  index_in_hard_unsat_clause[last_unsat_clause] = index;
}

inline void Decimation::hard_random_propagation() {
  int v, sense, temp_var;

  int c = hard_unsat_clause[rand() % hard_unsat_clause_count];
  v = clause_lit[c][0].var_num;
  sense = clause_lit[c][0].sense;

  for (int i = 1; i < clause_lit_count[c]; ++i) {
    temp_var = clause_lit[c][i].var_num;
    if (fix[temp_var] == -1) {
      v = temp_var;
      sense = clause_lit[c][i].sense;
      break;
    }
  }

  if (fix[v] != -1) {
    remove_assigned_hard_clause(c);
    return;
  }

  assign(v, sense);
}

inline void Decimation::unit_prosess() {
  while (unassigned_var_count > 0) {
    if (hunit_beg_pointer != hunit_end_pointer) {
      hunit_propagation();
    } else if (sunit_beg_pointer != sunit_end_pointer) {
      sunit_propagation();
    } else {
      random_propagation();
    }
  }
}

inline void Decimation::hard_unit_prosess() {
  while (unassigned_var_count > 0) {
    if (hunit_beg_pointer != hunit_end_pointer) {
      hunit_propagation();
    } else if (sunit_beg_pointer != sunit_end_pointer) {
      sunit_propagation();
    } else if (hard_unsat_clause_count > 0) {
      hard_random_propagation();
    } else {
      random_propagation();
    }
  }
}

class DeepDist {
 public:
  /***********non-algorithmic information ****************/
  int problem_weighted;

  int num_vars;
  int num_clauses;
  int num_hclauses;
  int num_sclauses;

  int tries;
  int max_tries;
  unsigned int max_flips;
  unsigned int max_non_improve_flip;
  unsigned int step;

  int print_time;
  int cutoff_time;
  int prioup_time;
  double opt_time;

  /**********end non-algorithmic information*****************/
  lit **var_lit;
  int *var_lit_count;
  lit **clause_lit;
  int *clause_lit_count;

  double *score;
  long long *time_stamp;
  int **var_neighbor;
  int *var_neighbor_count;
  int *neighbor_flag;
  int *temp_neighbor;

  long long top_clause_weight;
  long long *org_clause_weight;
  long long total_soft_weight;
  long long max_soft_weight;
  long long min_soft_weight;
  double *clause_weight;
  double *tuned_org_clause_weight;
  double coe_tuned_weight;
  int *sat_count;
  int *sat_var;

  int *soft_clause_num_index;
  double avg_soft_weight;
  double max_soft_clause_weight;
  double soft_increase_ratio;

  int *best_soft_clause;
  long long total_soft_length;
  long long total_hard_length;

  lit *unit_clause;
  int unit_clause_count;

  int *hardunsat_stack;
  int *index_in_hardunsat_stack;
  int hardunsat_stack_fill_pointer;

  int *softunsat_stack;
  int *index_in_softunsat_stack;
  int softunsat_stack_fill_pointer;

  int *unsatvar_stack;
  int unsatvar_stack_fill_pointer;
  int *index_in_unsatvar_stack;
  int *unsat_app_count;

  int *goodvar_stack;
  int goodvar_stack_fill_pointer;
  int *already_in_goodvar_stack;

  int *cur_soln;
  int *best_soln;
  int *local_opt_soln;
  int best_soln_feasible;
  int local_soln_feasible;
  int hard_unsat_nb;
  long long soft_unsat_weight;
  long long opt_unsat_weight;
  long long local_opt_unsat_weight;

  int *large_weight_clauses;
  int large_weight_clauses_count;
  int large_clause_count_threshold;

  int *soft_large_weight_clauses;
  int *already_in_soft_large_weight_stack;
  int soft_large_weight_clauses_count;
  int soft_large_clause_count_threshold;

  int *best_array;
  int best_count;
  int *temp_lit;

  float rwprob;
  float rdprob;
  float smooth_probability;
  float soft_smooth_probability;
  int hd_count_threshold;
  double h_inc;
  double s_inc;
  double h_inc_1;
  double h_inc_2;
  double s_inc_1;
  double s_inc_2;
  double softclause_weight_threshold;
  float random_prob;
  int coe_soft_clause_weight;

  int DEEPDIST_TIME_LIMIT;

  void build_neighbor_relation();
  void allocate_memory();

  void hard_increase_weights();
  void soft_increase_weights();
  void smooth_weights();
  void hard_smooth_weights();
  void soft_smooth_weights();
  void update_clause_weights();
  void unsat(int clause);
  void sat(int clause);
  void init(vector<int> &init_solution);
  void flip(int flipvar);
  void update_goodvarstack1(int flipvar);
  void update_goodvarstack2(int flipvar);
  int pick_var();
  void soft_increase_weights_not_partial();

  DeepDist();
  void settings();
  void build_instance(char *filename);
  void build_instance(int numVars, int numClauses,
                      unsigned long long topClauseweight, lit **dd_clause,
                      int *dd_clause_lit_count,
                      unsigned long long *dd_clause_weight);
  void local_search_with_decimation(char *inputfile);
  void simple_print(char *filename);
  void print_best_solution();
  void free_memory();
  bool verify_sol();
  bool parse_parameters2(int argc, char **argv);

 private:
  bool built_from_file_ =
      false;  // track how instance was built for free_memory
  Logger &logger_ = Logger::Instance();
};

inline DeepDist::DeepDist() {}

inline void DeepDist::settings() {
  local_soln_feasible = 1;
  DEEPDIST_TIME_LIMIT = 15;
  cutoff_time = 300;
  max_tries = 100000000;
  max_flips = 200000000;
  max_non_improve_flip = 10000000;
  large_clause_count_threshold = 0;
  soft_large_clause_count_threshold = 0;

  if (1 == problem_weighted) {
    coe_soft_clause_weight = 3000;
    if (0 != num_hclauses) {
      DEEPDIST_TIME_LIMIT = 20;
      hd_count_threshold = 97;
      rdprob = 0.036;
      rwprob = 0.48;
      h_inc = 28;
      soft_increase_ratio = 1.001;
      avg_soft_weight = double(total_soft_weight) / num_sclauses;
      for (int i = 0; i < num_sclauses; ++i) {
        int c = soft_clause_num_index[i];
        tuned_org_clause_weight[c] =
            (double)org_clause_weight[c] / avg_soft_weight;
      }
    } else {
      DEEPDIST_TIME_LIMIT = 25;
      softclause_weight_threshold = 0;
      soft_smooth_probability = 1E-3;
      hd_count_threshold = 22;
      rdprob = 0.036;
      rwprob = 0.48;
      s_inc = 1.0;
      for (int i = 0; i < num_sclauses; ++i) {
        int c = soft_clause_num_index[i];
        tuned_org_clause_weight[c] = org_clause_weight[c];
      }
    }
  } else {
    avg_soft_weight = 1;
    for (int i = 0; i < num_sclauses; ++i) {
      int c = soft_clause_num_index[i];
      tuned_org_clause_weight[c] = 1;
    }
    h_inc = 1;
    s_inc = 1;
    if (0 != num_hclauses) {
      hd_count_threshold = 53;
      coe_soft_clause_weight = 1;
      rdprob = 0.079;
      rwprob = 0.087;
      soft_increase_ratio = 1.00072;
    } else {
      hd_count_threshold = 94;
      coe_soft_clause_weight = 397;
      rdprob = 0.007;
      rwprob = 0.047;
      soft_smooth_probability = 0.002;
      softclause_weight_threshold = 550;
    }
  }
}

inline void DeepDist::build_neighbor_relation() {
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

inline void DeepDist::build_instance(char *filename) {
  built_from_file_ = true;
  total_soft_length = 0;
  total_hard_length = 0;
  istringstream iss;
  string line;
  char tempstr1[10];
  char tempstr2[10];

  ifstream infile(filename);
  if (!infile) {
    cout << "c the input filename " << filename
         << " is invalid, please input the correct filename." << endl;
    exit(-1);
  }

  while (getline(infile, line)) {
    if (line[3] == 'n' && line[4] == 'v' && line[5] == 'a' && line[6] == 'r' &&
        line[7] == 's') {
      line[line.length() - 1] = '\0';
      sscanf(line.c_str(), "%s %s %d", tempstr1, tempstr2, &num_vars);
    }

    if (line[3] == 'n' && line[4] == 'c' && line[5] == 'l' && line[6] == 's') {
      line[line.length() - 1] = '\0';
      sscanf(line.c_str(), "%s %s %d", tempstr1, tempstr2, &num_clauses);
      break;
    }
  }

  allocate_memory();

  int v, c;
  for (c = 0; c < num_clauses; c++) {
    clause_lit_count[c] = 0;
    clause_lit[c] = NULL;
  }
  for (v = 1; v <= num_vars; ++v) {
    var_lit_count[v] = 0;
    var_lit[v] = NULL;
    var_neighbor[v] = NULL;
  }

  int cur_lit;
  c = 0;
  problem_weighted = 0;
  num_hclauses = num_sclauses = 0;
  unit_clause_count = 0;

  int *redunt_test = new int[num_vars + 1];
  memset(redunt_test, 0, sizeof(int) * (num_vars + 1));
  top_clause_weight = __LONG_LONG_MAX__;
  total_soft_weight = 0;
  while (getline(infile, line)) {
    if (line[0] == 'c')
      continue;
    else if (line[0] == 'p') {
      int read_items;
      num_vars = num_clauses = 0;
      read_items = sscanf(line.c_str(), "%s %s %d %d %lld", tempstr1, tempstr2,
                          &num_vars, &num_clauses, &top_clause_weight);

      if (read_items < 5) {
        cout << "read item < 5 " << endl;
        exit(-1);
      }
      iss.clear();
      iss.str(line);
      iss.seekg(0, ios::beg);
      continue;
    } else {
      iss.clear();
      iss.str(line);
      iss.seekg(0, ios::beg);
    }
    clause_lit_count[c] = 0;

    if (line[0] == 'h') {
      iss >> tempstr1;
      org_clause_weight[c] = __LONG_LONG_MAX__;
    } else
      iss >> org_clause_weight[c];
    if (org_clause_weight[c] != top_clause_weight) {
      if (org_clause_weight[c] != 1) problem_weighted = 1;
      total_soft_weight += org_clause_weight[c];
      soft_clause_num_index[num_sclauses++] = c;
    } else {
      num_hclauses++;
    }

    iss >> cur_lit;
    int clause_reduent = 0;
    while (cur_lit != 0) {
      if (redunt_test[abs(cur_lit)] == 0) {
        temp_lit[clause_lit_count[c]] = cur_lit;
        clause_lit_count[c]++;
        redunt_test[abs(cur_lit)] = cur_lit;
      } else if (redunt_test[abs(cur_lit)] != cur_lit) {
        clause_reduent = 1;
        break;
      }
      iss >> cur_lit;
    }
    if (clause_reduent == 1) {
      for (int i = 0; i < clause_lit_count[c]; ++i)
        redunt_test[abs(temp_lit[i])] = 0;

      num_clauses--;
      clause_lit_count[c] = 0;
      continue;
    }

    clause_lit[c] = new lit[clause_lit_count[c] + 1];

    int i;
    for (i = 0; i < clause_lit_count[c]; ++i) {
      clause_lit[c][i].clause_num = c;
      v = abs(temp_lit[i]);
      clause_lit[c][i].var_num = v;
      redunt_test[v] = 0;
      if (temp_lit[i] > 0)
        clause_lit[c][i].sense = 1;
      else
        clause_lit[c][i].sense = 0;

      var_lit_count[v]++;
    }
    clause_lit[c][i].var_num = 0;
    clause_lit[c][i].clause_num = -1;

    if (clause_lit_count[c] == 1)
      unit_clause[unit_clause_count++] = clause_lit[c][0];
    if (top_clause_weight == org_clause_weight[c]) {
      total_hard_length += clause_lit_count[c];
    } else {
      total_soft_length += clause_lit_count[c];
    }
    c++;
  }

  infile.close();
  delete[] redunt_test;

  for (v = 1; v <= num_vars; ++v) {
    var_lit[v] = new lit[var_lit_count[v] + 1];
    var_lit_count[v] = 0;
  }
  for (c = 0; c < num_clauses; ++c) {
    for (int i = 0; i < clause_lit_count[c]; ++i) {
      v = clause_lit[c][i].var_num;
      var_lit[v][var_lit_count[v]] = clause_lit[c][i];
      ++var_lit_count[v];
    }
  }
  for (v = 1; v <= num_vars; ++v) var_lit[v][var_lit_count[v]].clause_num = -1;

  best_soln_feasible = 0;
}

inline void DeepDist::build_instance(int numVars, int numClauses,
                                     unsigned long long topClauseweight,
                                     lit **dd_clause, int *dd_clause_lit_count,
                                     unsigned long long *dd_clause_weight) {
  built_from_file_ = false;
  total_soft_length = 0;
  total_hard_length = 0;
  num_vars = numVars;
  num_clauses = numClauses;
  top_clause_weight = topClauseweight;

  allocate_memory();

  int v, c;
  for (v = 1; v <= num_vars; ++v) {
    var_lit_count[v] = 0;
    var_lit[v] = NULL;
    var_neighbor[v] = NULL;
  }

  // Copy clause data from the provided arrays
  for (c = 0; c < num_clauses; ++c) {
    clause_lit_count[c] = dd_clause_lit_count[c];
    clause_lit[c] = dd_clause[c];  // take ownership of the pointer
    org_clause_weight[c] = dd_clause_weight[c];
  }

  problem_weighted = 0;
  num_hclauses = num_sclauses = 0;
  unit_clause_count = 0;
  total_soft_weight = 0;

  for (c = 0; c < num_clauses; ++c) {
    if (org_clause_weight[c] != top_clause_weight) {
      if (org_clause_weight[c] != 1) problem_weighted = 1;
      total_soft_weight += org_clause_weight[c];
      soft_clause_num_index[num_sclauses++] = c;
    } else {
      num_hclauses++;
    }

    for (int j = 0; j < clause_lit_count[c]; ++j) {
      var_lit_count[clause_lit[c][j].var_num]++;
    }

    if (clause_lit_count[c] == 1)
      unit_clause[unit_clause_count++] = clause_lit[c][0];

    if (top_clause_weight == org_clause_weight[c]) {
      total_hard_length += clause_lit_count[c];
    } else {
      total_soft_length += clause_lit_count[c];
    }
  }

  // create var literal arrays
  for (v = 1; v <= num_vars; ++v) {
    var_lit[v] = new lit[var_lit_count[v] + 1];
    var_lit_count[v] = 0;
  }
  // scan all clauses to build up var literal arrays
  for (c = 0; c < num_clauses; ++c) {
    for (int i = 0; i < clause_lit_count[c]; ++i) {
      v = clause_lit[c][i].var_num;
      var_lit[v][var_lit_count[v]] = clause_lit[c][i];
      ++var_lit_count[v];
    }
  }
  for (v = 1; v <= num_vars; ++v) var_lit[v][var_lit_count[v]].clause_num = -1;

  best_soln_feasible = 0;
  opt_unsat_weight = total_soft_weight + 1;
}

inline void DeepDist::allocate_memory() {
  int malloc_var_length = num_vars + 10;
  int malloc_clause_length = num_clauses + 10;

  unit_clause = new lit[malloc_clause_length];

  var_lit = new lit *[malloc_var_length];
  var_lit_count = new int[malloc_var_length];
  clause_lit = new lit *[malloc_clause_length];
  clause_lit_count = new int[malloc_clause_length];

  score = new double[malloc_var_length];
  var_neighbor = new int *[malloc_var_length];
  for (int i = 0; i < malloc_var_length; i++) {
    var_neighbor[i] = NULL;
  }
  var_neighbor_count = new int[malloc_var_length];
  time_stamp = new long long[malloc_var_length];
  neighbor_flag = new int[malloc_var_length];
  temp_neighbor = new int[malloc_var_length];

  org_clause_weight = new long long[malloc_clause_length];
  clause_weight = new double[malloc_clause_length];
  tuned_org_clause_weight = new double[malloc_clause_length];
  sat_count = new int[malloc_clause_length];
  sat_var = new int[malloc_clause_length];
  best_soft_clause = new int[malloc_clause_length];

  hardunsat_stack = new int[malloc_clause_length];
  index_in_hardunsat_stack = new int[malloc_clause_length];
  softunsat_stack = new int[malloc_clause_length];
  index_in_softunsat_stack = new int[malloc_clause_length];

  unsatvar_stack = new int[malloc_var_length];
  index_in_unsatvar_stack = new int[malloc_var_length];
  unsat_app_count = new int[malloc_var_length];

  goodvar_stack = new int[malloc_var_length];
  already_in_goodvar_stack = new int[malloc_var_length];

  cur_soln = new int[malloc_var_length];
  best_soln = new int[malloc_var_length];
  local_opt_soln = new int[malloc_var_length];

  large_weight_clauses = new int[malloc_clause_length];
  soft_large_weight_clauses = new int[malloc_clause_length];
  already_in_soft_large_weight_stack = new int[malloc_clause_length];

  best_array = new int[malloc_var_length];
  temp_lit = new int[malloc_var_length];

  soft_clause_num_index = new int[malloc_clause_length];
}

inline void DeepDist::free_memory() {
  int i;
  for (i = 0; i < num_clauses; i++) delete[] clause_lit[i];

  for (i = 1; i <= num_vars; ++i) {
    delete[] var_lit[i];
    if (var_neighbor[i] != NULL) delete[] var_neighbor[i];
  }

  delete[] unit_clause;

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
  delete[] tuned_org_clause_weight;
  delete[] sat_count;
  delete[] sat_var;
  delete[] best_soft_clause;

  delete[] hardunsat_stack;
  delete[] index_in_hardunsat_stack;
  delete[] softunsat_stack;
  delete[] index_in_softunsat_stack;

  delete[] unsatvar_stack;
  delete[] index_in_unsatvar_stack;
  delete[] unsat_app_count;

  delete[] goodvar_stack;
  delete[] already_in_goodvar_stack;

  delete[] cur_soln;
  delete[] best_soln;
  delete[] local_opt_soln;

  delete[] large_weight_clauses;
  delete[] soft_large_weight_clauses;
  delete[] already_in_soft_large_weight_stack;

  delete[] best_array;
  delete[] temp_lit;

  delete[] soft_clause_num_index;
}

inline void DeepDist::update_goodvarstack1(int flipvar) {
  int v;
  for (int index = goodvar_stack_fill_pointer - 1; index >= 0; index--) {
    v = goodvar_stack[index];
    if (score[v] <= 0) {
      goodvar_stack[index] = mypop(goodvar_stack);
      already_in_goodvar_stack[v] = -1;
    }
  }

  for (int i = 0; i < var_neighbor_count[flipvar]; ++i) {
    v = var_neighbor[flipvar][i];
    if (score[v] > 0) {
      if (already_in_goodvar_stack[v] == -1) {
        already_in_goodvar_stack[v] = goodvar_stack_fill_pointer;
        mypush(v, goodvar_stack);
      }
    }
  }
}

inline void DeepDist::update_goodvarstack2(int flipvar) {
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
  int i, v;
  for (i = 0; i < var_neighbor_count[flipvar]; ++i) {
    v = var_neighbor[flipvar][i];
    if (score[v] > 0) {
      if (already_in_goodvar_stack[v] == -1) {
        already_in_goodvar_stack[v] = goodvar_stack_fill_pointer;
        mypush(v, goodvar_stack);
      }
    } else if (already_in_goodvar_stack[v] != -1) {
      int index = already_in_goodvar_stack[v];
      int last_v = mypop(goodvar_stack);
      goodvar_stack[index] = last_v;
      already_in_goodvar_stack[last_v] = index;
      already_in_goodvar_stack[v] = -1;
    }
  }
}

inline void DeepDist::flip(int flipvar) {
  int i, v, c;
  lit *clause_c;

  double org_flipvar_score = score[flipvar];
  cur_soln[flipvar] = 1 - cur_soln[flipvar];

  for (i = 0; i < var_lit_count[flipvar]; ++i) {
    c = var_lit[flipvar][i].clause_num;
    clause_c = clause_lit[c];

    if (cur_soln[flipvar] == (int)var_lit[flipvar][i].sense) {
      ++sat_count[c];
      if (sat_count[c] == 2) {
        score[sat_var[c]] += clause_weight[c];
        if (score[sat_var[c]] > 0 &&
            -1 == already_in_goodvar_stack[sat_var[c]]) {
          already_in_goodvar_stack[sat_var[c]] = goodvar_stack_fill_pointer;
          mypush(sat_var[c], goodvar_stack);
        }
      } else if (sat_count[c] == 1) {
        sat_var[c] = flipvar;
        for (lit *p = clause_c; (v = p->var_num) != 0; p++) {
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
        for (lit *p = clause_c; (v = p->var_num) != 0; p++) {
          if (p->sense == cur_soln[v]) {
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
        for (lit *p = clause_c; (v = p->var_num) != 0; p++) {
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

inline void DeepDist::print_best_solution() {
  if (best_soln_feasible == 0) return;

  printf("v ");
  for (int i = 1; i <= num_vars; i++) {
    if (best_soln[i] == 0)
      printf("0");
    else
      printf("1");
  }
  printf("\n");
}

inline bool DeepDist::verify_sol() {
  int c, j, flag;
  long long verify_unsat_weight = 0;

  for (c = 0; c < num_clauses; ++c) {
    flag = 0;
    for (j = 0; j < clause_lit_count[c]; ++j)
      if (best_soln[clause_lit[c][j].var_num] == (int)clause_lit[c][j].sense) {
        flag = 1;
        break;
      }

    if (flag == 0) {
      if (org_clause_weight[c] == top_clause_weight) {
        cout << "c Error: hard clause " << c << " is not satisfied" << endl;

        cout << "c ";
        for (j = 0; j < clause_lit_count[c]; ++j) {
          if (clause_lit[c][j].sense == 0) cout << "-";
          cout << clause_lit[c][j].var_num << " ";
        }
        cout << endl;
        cout << "c ";
        for (j = 0; j < clause_lit_count[c]; ++j)
          cout << best_soln[clause_lit[c][j].var_num] << " ";
        cout << endl;
        return 0;
      } else {
        verify_unsat_weight += org_clause_weight[c];
      }
    }
  }

  if (verify_unsat_weight == opt_unsat_weight)
    return 1;
  else {
    cout << "c Error: find opt=" << opt_unsat_weight
         << ", but verified opt=" << verify_unsat_weight << endl;
  }
  return 0;
}

inline void DeepDist::simple_print(char *filename) {
  if (best_soln_feasible != 0) {
    if (verify_sol() == 1) {
      cout << opt_unsat_weight << '\t' << opt_time << endl;
    } else
      cout << "solution is wrong " << endl;
  } else {
    cout << -1 << '\t' << -1 << endl;
  }
}

inline void DeepDist::unsat(int clause) {
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

inline void DeepDist::sat(int clause) {
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

inline void DeepDist::init(vector<int> &init_solution) {
  soft_large_weight_clauses_count = 0;

  if (1 == problem_weighted) {
    for (int c = 0; c < num_clauses; c++) {
      already_in_soft_large_weight_stack[c] = 0;

      if (num_hclauses > 0) {
        if ((0 == local_soln_feasible || 0 == best_soln_feasible)) {
          if (org_clause_weight[c] == top_clause_weight)
            clause_weight[c] = 1;
          else
            clause_weight[c] = 0;
        } else {
          if (org_clause_weight[c] == top_clause_weight)
            clause_weight[c] = 1;
          else
            clause_weight[c] = tuned_org_clause_weight[c];
        }
      } else {
        clause_weight[c] = tuned_org_clause_weight[c];
        if (clause_weight[c] > s_inc &&
            already_in_soft_large_weight_stack[c] == 0) {
          already_in_soft_large_weight_stack[c] = 1;
          soft_large_weight_clauses[soft_large_weight_clauses_count++] = c;
        }
      }
    }
  } else {
    for (int c = 0; c < num_clauses; c++) {
      already_in_soft_large_weight_stack[c] = 0;

      if (num_hclauses > 0) {
        if ((0 == local_soln_feasible || 0 == best_soln_feasible)) {
          if (org_clause_weight[c] == top_clause_weight)
            clause_weight[c] = 1;
          else
            clause_weight[c] = 0;
        } else {
          if (org_clause_weight[c] == top_clause_weight)
            clause_weight[c] = 0;
          else
            clause_weight[c] = 1;
        }
      } else {
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
      unsat_app_count[v] = 0;
    }
  } else {
    for (int v = 1; v <= num_vars; v++) {
      cur_soln[v] = init_solution[v];
      if (cur_soln[v] != 0 && cur_soln[v] != 1) cur_soln[v] = rand() % 2;
      time_stamp[v] = 0;
      unsat_app_count[v] = 0;
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
      if (cur_soln[clause_lit[c][j].var_num] == (int)clause_lit[c][j].sense) {
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
  for (int v = 1; v <= num_vars; v++) {
    if (score[v] > 0) {
      already_in_goodvar_stack[v] = goodvar_stack_fill_pointer;
      mypush(v, goodvar_stack);
    } else
      already_in_goodvar_stack[v] = -1;
  }
}

inline int DeepDist::pick_var() {
  int i, v;
  int best_var;
  int sel_c;
  lit *p;

  if (goodvar_stack_fill_pointer > 0) {
    if ((rand() % MY_RAND_MAX_INT) * BASIC_SCALE < rdprob)
      return goodvar_stack[rand() % goodvar_stack_fill_pointer];

    if (goodvar_stack_fill_pointer < hd_count_threshold) {
      best_var = goodvar_stack[0];

      for (i = 1; i < goodvar_stack_fill_pointer; ++i) {
        v = goodvar_stack[i];
        if (score[v] > score[best_var]) {
          best_var = v;
        } else if (score[v] == score[best_var]) {
          if (time_stamp[v] < time_stamp[best_var]) {
            best_var = v;
          }
        }
      }
      return best_var;
    } else {
      best_var = goodvar_stack[rand() % goodvar_stack_fill_pointer];

      for (i = 1; i < hd_count_threshold; ++i) {
        v = goodvar_stack[rand() % goodvar_stack_fill_pointer];
        if (score[v] > score[best_var]) {
          best_var = v;
        } else if (score[v] == score[best_var]) {
          if (time_stamp[v] < time_stamp[best_var]) {
            best_var = v;
          }
        }
      }
      return best_var;
    }
  }

  update_clause_weights();

  if (hardunsat_stack_fill_pointer > 0) {
    sel_c = hardunsat_stack[rand() % hardunsat_stack_fill_pointer];
  } else {
    while (1) {
      sel_c = softunsat_stack[rand() % softunsat_stack_fill_pointer];
      if (clause_lit_count[sel_c] != 0) break;
    }
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

inline void DeepDist::local_search_with_decimation(char *inputfile) {
  Decimation deci(var_lit, var_lit_count, clause_lit, org_clause_weight,
                  top_clause_weight);
  deci.make_space(num_clauses, num_vars);
  long long total_step = 0;
  opt_unsat_weight = __LONG_LONG_MAX__;
  for (tries = 1; tries < max_tries; ++tries) {
    deci.init(local_opt_soln, best_soln, unit_clause, unit_clause_count,
              clause_lit_count);

    if (1 == problem_weighted)
      deci.unit_prosess();
    else
      deci.hard_unit_prosess();

    init(deci.fix);

    long long local_opt = __LONG_LONG_MAX__;
    max_flips = max_non_improve_flip;
    for (step = 1; step < max_flips; ++step) {
      if (hard_unsat_nb == 0) {
        local_soln_feasible = 1;
        if (local_opt > soft_unsat_weight) {
          local_opt = soft_unsat_weight;
          max_flips = step + max_non_improve_flip;
        }
        if (soft_unsat_weight < opt_unsat_weight) {
          opt_time = dd_get_runtime();
          cout << "o " << soft_unsat_weight << endl;
          opt_unsat_weight = soft_unsat_weight;
          for (int v = 1; v <= num_vars; ++v) best_soln[v] = cur_soln[v];
        }
        if (best_soln_feasible == 0) {
          best_soln_feasible = 1;
        }
      }
      int flipvar = pick_var();
      flip(flipvar);
      time_stamp[flipvar] = step;
      total_step++;
    }
  }
}

inline void DeepDist::hard_increase_weights() {
  int i, c, v;
  for (i = 0; i < hardunsat_stack_fill_pointer; ++i) {
    c = hardunsat_stack[i];

    clause_weight[c] += h_inc;

    if (clause_weight[c] == (h_inc + 1))
      large_weight_clauses[large_weight_clauses_count++] = c;

    for (lit *p = clause_lit[c]; (v = p->var_num) != 0; p++) {
      score[v] += h_inc;
      if (score[v] > 0 && already_in_goodvar_stack[v] == -1) {
        already_in_goodvar_stack[v] = goodvar_stack_fill_pointer;
        mypush(v, goodvar_stack);
      }
    }
  }
  return;
}

inline void DeepDist::soft_increase_weights() {
  int i, c, v;

  if (1 == problem_weighted) {
    for (i = 0; i < num_sclauses; ++i) {
      c = soft_clause_num_index[i];

      double inc = soft_increase_ratio *
                       (clause_weight[c] + tuned_org_clause_weight[c]) -
                   clause_weight[c];

      clause_weight[c] += inc;
      if (sat_count[c] <= 0) {
        for (lit *p = clause_lit[c]; (v = p->var_num) != 0; p++) {
          score[v] += inc;
          if (score[v] > 0 && already_in_goodvar_stack[v] == -1) {
            already_in_goodvar_stack[v] = goodvar_stack_fill_pointer;
            mypush(v, goodvar_stack);
          }
        }
      } else if (sat_count[c] < 2) {
        v = sat_var[c];
        score[v] -= inc;
        if (score[v] <= 0 && -1 != already_in_goodvar_stack[v]) {
          int index = already_in_goodvar_stack[v];
          int last_v = mypop(goodvar_stack);
          goodvar_stack[index] = last_v;
          already_in_goodvar_stack[last_v] = index;
          already_in_goodvar_stack[v] = -1;
        }
      }
    }
  } else {
    for (i = 0; i < num_sclauses; ++i) {
      c = soft_clause_num_index[i];

      double inc =
          soft_increase_ratio * (clause_weight[c] + s_inc) - clause_weight[c];

      clause_weight[c] += inc;

      if (sat_count[c] <= 0) {
        for (lit *p = clause_lit[c]; (v = p->var_num) != 0; p++) {
          score[v] += inc;
          if (score[v] > 0 && already_in_goodvar_stack[v] == -1) {
            already_in_goodvar_stack[v] = goodvar_stack_fill_pointer;
            mypush(v, goodvar_stack);
          }
        }
      } else if (sat_count[c] < 2) {
        v = sat_var[c];
        score[v] -= inc;
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
  return;
}

inline void DeepDist::soft_smooth_weights() {
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

inline void DeepDist::soft_increase_weights_not_partial() {
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
      for (lit *p = clause_lit[c]; (v = p->var_num) != 0; p++) {
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
      for (lit *p = clause_lit[c]; (v = p->var_num) != 0; p++) {
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

inline void DeepDist::update_clause_weights() {
  if (num_hclauses > 0) {
    hard_increase_weights();

    if (1 == problem_weighted) {
      if (0 == hard_unsat_nb) {
        soft_increase_weights();
      }
    } else {
      if (soft_unsat_weight >= opt_unsat_weight && best_soln_feasible != 0) {
        soft_increase_weights();
      }
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

}  // namespace deepdist