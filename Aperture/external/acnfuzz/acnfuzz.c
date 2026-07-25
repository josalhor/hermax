/* Copyright (c) 2009 - 2010, Armin Biere, Johannes Kepler University. */
/* Copyright (c) 2024 - 2025, Alexander Nadel, Technion. */

#include <assert.h>
#include <ctype.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/times.h>
#include <unistd.h>

#include <vector>

using namespace std;

#define MAX 20
static int clause[MAX + 1];

static int pick(int from, int to) {
  assert(from <= to);
  return (rand() % (to - from + 1)) + from;
}

static uint64_t pick_u64(uint64_t from, uint64_t to) {
  assert(from <= to);
  const uint64_t span = to - from + 1;
  uint64_t r = 0;
  // Build a 60-bit random value from rand() chunks.
  for (int i = 0; i < 4; ++i) {
    r <<= 15;
    r ^= (uint64_t)(rand() & 0x7fff);
  }
  return from + (r % span);
}

static int numstr(const char* str) {
  const char* p;
  for (p = str; *p; p++)
    if (!isdigit(*p)) return 0;
  return 1;
}

#define SIGN() ((pick(31, 32) == 32) ? -1 : 1)

int main(int argc, char** argv) {
  int i, j, k, l, m, n, o, p, sign, lit, layer, w, val, min, max, ospread;
  int **unused, *nunused, allmin, allmax, qbf, *quant, scramble, *map;
  int seed, nlayers, **layers, *width, *low, *high, *clauses;
  int fp, eqs, ands, *arity, maxarity, lhs, rhs;
  int p_sat, p_u, p_w;
  int soft_recent_ratio;
  int maxSoftLits;
  int recentPoolLimit;
  uint64_t maxWeightedSoftSum;
  const char* options;
  char option[100];
  FILE* file;
  char* mark;

  qbf = 0;
  seed = -1;
  options = 0;
  p_sat = 34;
  p_u = 33;
  p_w = 33;
  soft_recent_ratio = 50;
  maxSoftLits = 32;
  recentPoolLimit = 2048;
  maxWeightedSoftSum = UINT64_MAX - 1;

  for (i = 1; i < argc; i++) {
    if (!strcmp(argv[i], "-h")) {
      printf(
          "usage: cnfuzz_incr [-h][-q][<seed>][<option-file>]\n"
          "\n"
          "  -h   print command line option help\n"
          "  -q   generate quantified CNF in QDIMACS format\n"
          "  --p-sat <0..100>          probability weight for 's' queries\n"
          "  --p-u <0..100>            probability weight for 'u' queries\n"
          "  --p-w <0..100>            probability weight for 'w' queries\n"
          "  --soft-recent-ratio <0..100>  ratio of soft literals sampled from "
          "recent clauses\n"
          "  --max-soft-lits <n>       upper bound on #soft literals per u/w "
          "query\n"
          "  --recent-pool-limit <n>   keep at most n recent literals in soft "
          "pool\n"
          "  --max-weighted-soft-sum <n>   max allowed sum of weights in a w "
          "query\n"
          "\n"
          "If the seed is not specified it is calculated from the process id\n"
          "and the current system time (in seconds).\n"
          "\n"
          "The optional <option-file> lists integer options with their "
          "ranges,\n"
          "one option in the format '<opt> <lower> <upper> per line.\n"
          "Those options are fuzzed and embedded into the generated input\n"
          "in comments before the 'p cnf ...' header.\n");
      exit(0);
    }

    if (!strcmp(argv[i], "-q"))
      qbf = 1;
    else if (!strcmp(argv[i], "--p-sat")) {
      if (++i >= argc || !numstr(argv[i])) {
        fprintf(stderr, "*** cnfuzz: invalid --p-sat value\n");
        exit(1);
      }
      p_sat = atoi(argv[i]);
      if (p_sat < 0 || p_sat > 100) {
        fprintf(stderr, "*** cnfuzz: --p-sat must be in [0,100]\n");
        exit(1);
      }
    } else if (!strcmp(argv[i], "--p-u")) {
      if (++i >= argc || !numstr(argv[i])) {
        fprintf(stderr, "*** cnfuzz: invalid --p-u value\n");
        exit(1);
      }
      p_u = atoi(argv[i]);
      if (p_u < 0 || p_u > 100) {
        fprintf(stderr, "*** cnfuzz: --p-u must be in [0,100]\n");
        exit(1);
      }
    } else if (!strcmp(argv[i], "--p-w")) {
      if (++i >= argc || !numstr(argv[i])) {
        fprintf(stderr, "*** cnfuzz: invalid --p-w value\n");
        exit(1);
      }
      p_w = atoi(argv[i]);
      if (p_w < 0 || p_w > 100) {
        fprintf(stderr, "*** cnfuzz: --p-w must be in [0,100]\n");
        exit(1);
      }
    } else if (!strcmp(argv[i], "--soft-recent-ratio")) {
      if (++i >= argc || !numstr(argv[i])) {
        fprintf(stderr, "*** cnfuzz: invalid --soft-recent-ratio value\n");
        exit(1);
      }
      soft_recent_ratio = atoi(argv[i]);
      if (soft_recent_ratio < 0 || soft_recent_ratio > 100) {
        fprintf(stderr, "*** cnfuzz: --soft-recent-ratio must be in [0,100]\n");
        exit(1);
      }
    } else if (!strcmp(argv[i], "--max-soft-lits")) {
      if (++i >= argc || !numstr(argv[i])) {
        fprintf(stderr, "*** cnfuzz: invalid --max-soft-lits value\n");
        exit(1);
      }
      maxSoftLits = atoi(argv[i]);
      if (maxSoftLits < 0) {
        fprintf(stderr, "*** cnfuzz: --max-soft-lits must be >= 0\n");
        exit(1);
      }
    } else if (!strcmp(argv[i], "--recent-pool-limit")) {
      if (++i >= argc || !numstr(argv[i])) {
        fprintf(stderr, "*** cnfuzz: invalid --recent-pool-limit value\n");
        exit(1);
      }
      recentPoolLimit = atoi(argv[i]);
      if (recentPoolLimit <= 0) {
        fprintf(stderr, "*** cnfuzz: --recent-pool-limit must be > 0\n");
        exit(1);
      }
    } else if (!strcmp(argv[i], "--max-weighted-soft-sum")) {
      if (++i >= argc || !numstr(argv[i])) {
        fprintf(stderr, "*** cnfuzz: invalid --max-weighted-soft-sum value\n");
        exit(1);
      }
      maxWeightedSoftSum = strtoull(argv[i], 0, 10);
      if (maxWeightedSoftSum == 0) {
        fprintf(stderr, "*** cnfuzz: --max-weighted-soft-sum must be > 0\n");
        exit(1);
      }
    } else if (numstr(argv[i])) {
      if (seed >= 0) {
        fprintf(stderr, "*** cnfuzz: multiple seeds\n");
        exit(1);
      }
      seed = atoi(argv[i]);
      if (seed < 0) {
        fprintf(stderr, "*** cnfuzz: seed overflow\n");
        exit(1);
      }
    } else if (options) {
      fprintf(stderr, "*** cnfuzz: multiple option files\n");
      exit(1);
    } else
      options = argv[i];
  }

  if (seed < 0) {
    const auto t0 = times(0);
    const auto pid = getpid();
    const auto rs = (t0 * pid) >> 1;
    const auto newseed = abs(rs);
    seed = newseed;
    printf(
        "c Fixing a negative seed: t0 = %d; pid = %d; rs = %d; newseed = %d; "
        "seed = %d\n",
        t0, pid, rs, newseed, seed);
  }

  srand(seed);
  printf("c seed %d\n", seed);
  fflush(stdout);
  if ((p_sat + p_u + p_w) <= 0) {
    fprintf(stderr,
            "*** cnfuzz: at least one of --p-sat/--p-u/--p-w must be > 0\n");
    exit(1);
  }

  printf("c query_mix p_sat=%d p_u=%d p_w=%d\n", p_sat, p_u, p_w);
  printf("c soft_recent_ratio %d\n", soft_recent_ratio);
  printf("c maxSoftLits %d\n", maxSoftLits);
  printf("c recentPoolLimit %d\n", recentPoolLimit);
  printf("c maxWeightedSoftSum %llu\n", (unsigned long long)maxWeightedSoftSum);

  if (qbf) {
    printf("c qbf\n");
    fp = pick(0, 3);
    if (fp) printf("c but forced to be propositional\n");
  }
  if (options) {
    file = fopen(options, "r");
    ospread = pick(0, 10);
    if ((allmin = pick(0, 1)))
      printf("c allmin\n");
    else if ((allmax = pick(0, 1)))
      printf("c allmax\n");
    printf("c %d ospread\n", ospread);
    if (!file) {
      fprintf(stderr, "*** cnfuzz: can not read '%s'\n", options);
      exit(1);
    }
    while (fscanf(file, "%s %d %d %d", option, &val, &min, &max) == 4) {
      if (!pick(0, ospread)) {
        if (allmin)
          val = min;
        else if (allmax)
          val = max;
        else
          val = pick(min, max);
      }
      printf("c --%s=%d\n", option, val);
    }
    fclose(file);
  }
  srand(seed);
  w = pick(10, 70);
  printf("c width %d\n", w);
  scramble = pick(-1, 1); /* TODO finish */
  printf("c scramble %d\n", scramble);
  nlayers = pick(1, 20);
  printf("c layers %d\n", nlayers);
  eqs = pick(0, 2) ? 0 : pick(0, 99);
  printf("c equalities %d\n", eqs);
  ands = pick(0, 1) ? 0 : pick(0, 99);
  printf("c ands %d\n", ands);

  layers = (int**)calloc(nlayers, sizeof *layers);
  quant = (int*)calloc(nlayers, sizeof *quant);
  width = (int*)calloc(nlayers, sizeof *width);
  low = (int*)calloc(nlayers, sizeof *low);
  high = (int*)calloc(nlayers, sizeof *high);
  clauses = (int*)calloc(nlayers, sizeof *clauses);
  unused = (int**)calloc(nlayers, sizeof *unused);
  nunused = (int*)calloc(nlayers, sizeof *nunused);
  for (i = 0; i < nlayers; i++) {
    width[i] = pick(10, w);
    quant[i] = (qbf && !fp) ? pick(-1, 1) : 0;
    low[i] = i ? high[i - 1] + 1 : 1;
    high[i] = low[i] + width[i] - 1;
    m = width[i];
    if (i) m += width[i - 1];
    n = (pick(300, 450) * m) / 100;
    clauses[i] = n;
    printf("c layer[%d] = [%d..%d] w=%d v=%d c=%d r=%.2f q=%d\n", i, low[i],
           high[i], width[i], m, n, n / (double)m, quant[i]);

    nunused[i] = 2 * (high[i] - low[i] + 1);
    unused[i] = (int*)calloc(nunused[i], sizeof *unused[i]);
    k = 0;
    for (j = low[i]; j <= high[i]; j++)
      for (sign = -1; sign <= 1; sign += 2) unused[i][k++] = sign * j;
    assert(k == nunused[i]);
  }
  arity = (int*)calloc(ands, sizeof *arity);
  maxarity = m / 2;
  if (maxarity >= MAX) maxarity = MAX - 1;
  for (i = 0; i < ands; i++) arity[i] = pick(2, maxarity);
  n = 0;
  for (i = 0; i < ands; i++) n += arity[i] + 1;
  m = high[nlayers - 1];
  mark = (char*)calloc(m + 1, 1);
  for (i = 0; i < nlayers; i++) n += clauses[i];
  n += 2 * eqs;

  // Incremental

  // No header for incremental
  // m: variables
  // n: clauses
  printf("c pcnf-line-variables-clauses %d %d\n", m, n);

  int clssSoFar = 0;

  const int maxAssumps = pick(1, m);
  printf("c maxAssumps %d\n", maxAssumps);

  int incBlockEveryNClss = pick(0, n);
  auto GetIncrBlocks = [&]() {
    return incBlockEveryNClss == 0 ? 0 : n / incBlockEveryNClss;
  };
  int maxQueriesPerBlock = pick(1, 100);

  auto GetAverage = [](int q) { return (1 + q) / 2; };
  auto GetExpectedQueries = [&]() {
    return GetAverage(GetIncrBlocks()) * GetAverage(maxQueriesPerBlock);
  };

  // incBlockEveryNClss == 0 --> no incremental queries at all
  const int expectedQueriesThreshold = 1000;
  // For the rest, make sure no more than expectedQueriesThreshold queries on
  // average
  if (incBlockEveryNClss != 0) {
    if (GetExpectedQueries() > expectedQueriesThreshold) {
      printf(
          "c expectedQueries %d > %d --> increasing incBlockEveryNClss %d "
          "(GetIncrBlocks = %d) and/or decreasing maxQueriesPerBlock %d\n",
          GetExpectedQueries(), expectedQueriesThreshold, incBlockEveryNClss,
          GetIncrBlocks(), maxQueriesPerBlock);
    }

    for (int expectedQueries = GetExpectedQueries();
         expectedQueries > expectedQueriesThreshold;
         expectedQueries = GetExpectedQueries()) {
      if (incBlockEveryNClss >= n) {
        assert(maxQueriesPerBlock > 1);
        --maxQueriesPerBlock;
      } else if (maxQueriesPerBlock <= 1) {
        assert(incBlockEveryNClss <= n);
        ++incBlockEveryNClss;
      } else {
        if (pick(0, 1)) {
          ++incBlockEveryNClss;
        } else {
          --maxQueriesPerBlock;
        }
      }
    }
  }

  printf(
      "c expectedQueries %d < %d; incBlockEveryNClss %d ; incrBlocks %d ; "
      "maxQueriesPerBlock %d\n",
      GetExpectedQueries(), expectedQueriesThreshold, incBlockEveryNClss,
      GetIncrBlocks(), maxQueriesPerBlock);

  vector<int> recentLits;
  recentLits.reserve(recentPoolLimit);

  auto PushRecentLit = [&](int l_) {
    if ((int)recentLits.size() >= recentPoolLimit) {
      recentLits.erase(recentLits.begin());
    }
    recentLits.push_back(l_);
  };

  auto PickRandomSignedLit = [&]() {
    int v_ = pick(1, m);
    int lit_ = pick(0, 1) ? v_ : -v_;
    assert(lit_ != 0);
    return lit_;
  };

  auto PickMixedSoftLit = [&]() {
    const bool use_recent =
        !recentLits.empty() && pick(1, 100) <= soft_recent_ratio;
    if (use_recent) {
      int l_ = recentLits[pick(0, (int)recentLits.size() - 1)];
      if (pick(0, 9) == 0) l_ = -l_;
      assert(l_ != 0);
      return l_;
    }
    return PickRandomSignedLit();
  };

  auto PickMaxWeightByMSEBuckets = [&]() -> uint64_t {
    const int b = pick(1, 25);
    if (b <= 5) return 1ULL;                         // [1,1], prob 1/5
    if (b <= 10) return pick_u64(2ULL, 32ULL);       // [2,32], prob 1/5
    if (b <= 15) return pick_u64(33ULL, 256ULL);     // [33,256], prob 1/5
    if (b <= 20) return pick_u64(257ULL, 65535ULL);  // [257,65535], prob 1/5
    if (b <= 24)
      return pick_u64(65536ULL, 4294967296ULL);  // [65536,2^32], prob 4/25
    return pick_u64(4294967297ULL,
                    9223372036854775807ULL);  // [2^32+1,2^63-1], prob 1/25
  };

  auto PrintSQuery = [&](const vector<int>& assumps) {
    printf("s ");
    for (auto l : assumps) {
      printf("%d ", l);
    }
    printf("0\n");
  };

  auto PrintUQuery = [&](const vector<int>& assumps) {
    int numSoft = maxSoftLits == 0 ? 0 : pick(0, maxSoftLits);
    printf("u %d %d ", (int)assumps.size(), numSoft);
    for (auto l_ : assumps) {
      printf("%d ", l_);
    }
    for (int s_ = 0; s_ < numSoft; ++s_) {
      const int soft_lit = PickMixedSoftLit();
      assert(soft_lit != 0);
      printf("%d ", soft_lit);
    }
    printf("0\n");
  };

  auto PrintWQuery = [&](const vector<int>& assumps) {
    const int requestedSoft = maxSoftLits == 0 ? 0 : pick(0, maxSoftLits);
    const uint64_t queryMaxWeight = PickMaxWeightByMSEBuckets();

    vector<pair<uint64_t, int>> weightedSofts;
    weightedSofts.reserve(requestedSoft);

    uint64_t sum = 0;
    for (int s_ = 0; s_ < requestedSoft; ++s_) {
      const uint64_t remaining = maxWeightedSoftSum - sum;
      if (remaining == 0) break;
      const uint64_t maxAllowedWeight =
          queryMaxWeight < remaining ? queryMaxWeight : remaining;
      if (maxAllowedWeight == 0) break;

      const uint64_t w_ = pick_u64(1ULL, maxAllowedWeight);
      const int l_ = PickMixedSoftLit();

      assert(w_ != 0);
      assert(l_ != 0);

      weightedSofts.emplace_back(w_, l_);
      sum += w_;
    }

    printf("w %d %d ", (int)assumps.size(), (int)weightedSofts.size());
    for (auto l_ : assumps) {
      printf("%d ", l_);
    }
    for (auto wl_ : weightedSofts) {
      printf("%llu %d ", (unsigned long long)wl_.first, wl_.second);
    }
    printf("0\n");
  };

  auto PrintQuery = [&](const vector<int>& assumps) {
    // For true QBF mode, stick to SAT-style incremental queries.
    if (qbf && !fp) {
      PrintSQuery(assumps);
      return;
    }

    const int total = p_sat + p_u + p_w;
    const int r = pick(1, total);
    if (r <= p_sat) {
      PrintSQuery(assumps);
    } else if (r <= p_sat + p_u) {
      PrintUQuery(assumps);
    } else {
      PrintWQuery(assumps);
    }
  };

  auto NewClause = [&]() {
    ++clssSoFar;
    if (incBlockEveryNClss != 0 && (clssSoFar % incBlockEveryNClss) == 0) {
      const auto maxAssumpsForThisBlock = pick(1, maxAssumps);
      vector<int> assumps;
      assumps.reserve(maxAssumpsForThisBlock);
      while (assumps.size() < maxAssumpsForThisBlock) {
        assumps.emplace_back(pick(1, m));
        if (pick(0, 1)) {
          assumps.back() = -assumps.back();
        }
      }

      const auto queriesInBlock = pick(1, maxQueriesPerBlock);

      for (int currQuery = 1; currQuery <= queriesInBlock; ++currQuery) {
        vector<int> currAssumps;
        for (auto a : assumps) {
          if (pick(0, 1)) {
            if (pick(0, 9)) {
              currAssumps.emplace_back(a);
            } else {
              currAssumps.emplace_back(-a);
            }
          }
        }
        PrintQuery(currAssumps);
      }
    }
  };

  map = (int*)calloc(2 * m + 1, sizeof *map);
  map += m;
  if (qbf && !fp)
    for (i = 0; i < nlayers; i++) {
      if (!i && !quant[0]) continue;
      fputc(quant[i] < 0 ? 'a' : 'e', stdout);
      for (j = low[i]; j <= high[i]; j++) printf(" %d", j);
      fputs(" 0\n", stdout);
    }
  for (i = 0; i < nlayers; i++) {
    for (j = 0; j < clauses[i]; j++) {
      l = 3;
      while (l < MAX && pick(17, 19) != 17) l++;
      vector<int> emitted_clause;
      emitted_clause.reserve(l);

      for (k = 0; k < l; k++) {
        layer = i;
        while (layer && pick(3, 4) == 3) layer--;
        if (nunused[layer]) {
          o = nunused[layer] - 1;
          p = pick(0, o);
          lit = unused[layer][p];
          if (mark[abs(lit)]) continue;
          nunused[layer] = o;
          if (p != o) unused[layer][p] = unused[layer][o];
        } else {
          lit = pick(low[layer], high[layer]);
          if (mark[lit]) continue;
          lit *= SIGN();
        }
        assert(lit != 0);
        clause[k] = lit;
        emitted_clause.push_back(lit);
        mark[abs(lit)] = 1;
        printf("%d ", lit);
      }
      printf("0\n");
      for (auto emitted_lit : emitted_clause) PushRecentLit(emitted_lit);
      NewClause();
      for (k = 0; k < l; k++) mark[abs(clause[k])] = 0;
    }
  }
  while (eqs-- > 0) {
    i = pick(0, nlayers - 1);
    j = pick(0, nlayers - 1);
    k = pick(low[i], high[i]);
    l = pick(low[j], high[j]);
    if (k == l) {
      eqs++;
      continue;
    }
    k *= SIGN();
    l *= SIGN();
    assert(k != 0);
    assert(l != 0);
    printf("%d %d 0\n", k, l);
    PushRecentLit(k);
    PushRecentLit(l);
    NewClause();
    printf("%d %d 0\n", -k, -l);
    PushRecentLit(-k);
    PushRecentLit(-l);
    NewClause();
  }
  while (--ands >= 0) {
    l = arity[ands];
    assert(l < MAX);
    i = pick(0, nlayers - 1);
    lhs = pick(low[i], high[i]);
    mark[lhs] = 1;
    lhs *= SIGN();
    assert(lhs != 0);
    clause[0] = lhs;
    vector<int> emitted_clause;
    emitted_clause.reserve(l + 1);
    emitted_clause.push_back(lhs);
    printf("%d ", lhs);
    for (k = 1; k <= l; k++) {
      j = pick(0, nlayers - 1);
      rhs = pick(low[j], high[j]);
      if (mark[rhs]) {
        k--;
        continue;
      }
      mark[rhs] = 1;
      rhs *= SIGN();
      assert(rhs != 0);
      clause[k] = rhs;
      emitted_clause.push_back(rhs);
      printf("%d ", rhs);
    }
    printf("0\n");
    for (auto emitted_lit : emitted_clause) PushRecentLit(emitted_lit);
    NewClause();
    for (k = 1; k <= l; k++) {
      printf("%d %d 0\n", -clause[0], -clause[k]);
      PushRecentLit(-clause[0]);
      PushRecentLit(-clause[k]);
      NewClause();
    }
    for (k = 0; k <= l; k++) mark[abs(clause[k])] = 0;
  }
  map -= m;
  free(map);
  free(mark);
  free(clauses);
  free(arity);
  free(high);
  free(low);
  free(width);
  free(nunused);
  free(quant);
  for (i = 0; i < nlayers; i++) free(layers[i]), free(unused[i]);
  free(layers);
  if (clssSoFar != n) {
    printf(
        "ERROR: clauses-so-far %d must be equal to pre-calculated clauses %d\n",
        clssSoFar, n);
  }
  printf("s 0");
  return 0;
}